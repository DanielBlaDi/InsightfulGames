import { useState } from 'react';
import type { FormEvent } from 'react';
import GamePage from '../GamePage';
import GameScreen from '../GameScreen';
import { SCENARIOS } from './scenarios';
import type { MockScenario } from './scenarios';
import { useMockGame } from './useMockGame';

const BAR =
  'px-gutter-mobile md:px-margin py-space-sm bg-surface-container flex flex-wrap items-center gap-space-sm border-b border-outline-variant/40';
const FIELD = 'rounded-lg border-outline-variant bg-surface text-on-surface font-body-sm text-body-sm py-1';
const BUTTON =
  'px-space-sm py-1 rounded-lg bg-surface-container-highest text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors cursor-pointer';

function MockGame({ scenario }: { scenario: MockScenario }) {
  const session = useMockGame(scenario);
  const played = session.state?.moves.length ?? 0;
  const next = scenario.plies[played];
  const finished = session.state?.status === 'finished';

  return (
    <>
      <p className="px-gutter-mobile md:px-margin pt-space-xs font-body-sm text-body-sm text-on-surface-variant">
        {finished
          ? 'Partida terminada. Pulsa Reiniciar para repetirla.'
          : next
            ? `Siguiente jugada del guion: ${next.uci.slice(0, 2)} → ${next.uci.slice(2, 4)}${
                next.promotes ? ' (elige pieza)' : ''
              }${next.by === 'bot' ? ' · la hace Botcito' : ''}`
            : 'Fin del guion: cualquier jugada será rechazada por el simulador.'}
      </p>
      <GamePage session={session} />
    </>
  );
}

function MockHarness() {
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const [run, setRun] = useState(0);
  const scenario = SCENARIOS.find((s) => s.id === scenarioId) ?? SCENARIOS[0];

  return (
    <>
      <div className={BAR}>
        <label className="font-label-md text-label-md text-on-surface-variant flex items-center gap-space-xs">
          Escenario
          <select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)} className={FIELD}>
            {SCENARIOS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => setRun(run + 1)} className={BUTTON}>
          Reiniciar
        </button>
      </div>
      <MockGame key={`${scenario.id}-${run}`} scenario={scenario} />
    </>
  );
}

/**
 * Prueba contra el Gateway real. El gameId y el token se escriben aquí y viven solo en
 * memoria: no pasan por la URL de la página ni se guardan en el navegador.
 */
function SocketHarness() {
  const [credentials, setCredentials] = useState<{ gameId: string; token: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const gameId = String(data.get('gameId') ?? '').trim();
    const token = String(data.get('token') ?? '').trim();
    if (!gameId || !token) return;
    setNotice(null);
    setCredentials({ gameId, token });
  };

  if (credentials) {
    return (
      <>
        <div className={BAR}>
          <span className="font-body-sm text-body-sm text-on-surface-variant">Partida {credentials.gameId}</span>
          <button type="button" onClick={() => setCredentials(null)} className={BUTTON}>
            Desconectar
          </button>
        </div>
        <GameScreen
          gameId={credentials.gameId}
          token={credentials.token}
          onUnauthorized={() => {
            setCredentials(null);
            setNotice('El Gateway rechazó el token (cierre 4401). Aquí la aplicación volvería al login.');
          }}
        />
      </>
    );
  }

  return (
    <form onSubmit={handleSubmit} autoComplete="off" className={BAR}>
      <label className="font-label-md text-label-md text-on-surface-variant flex items-center gap-space-xs">
        gameId
        <input name="gameId" required className={`${FIELD} w-72`} />
      </label>
      <label className="font-label-md text-label-md text-on-surface-variant flex items-center gap-space-xs">
        Token
        <input name="token" type="password" required autoComplete="off" className={`${FIELD} w-56`} />
      </label>
      <button type="submit" className={BUTTON}>
        Conectar
      </button>
      {notice && <span className="font-body-sm text-body-sm text-error">{notice}</span>}
    </form>
  );
}

export default function DevHarness() {
  const [source, setSource] = useState<'mock' | 'socket'>('mock');

  return (
    <div className="w-full min-h-screen bg-background">
      <div className={BAR}>
        <span className="px-2 py-0.5 rounded-full bg-tertiary/10 text-tertiary font-label-sm text-label-sm uppercase tracking-wider">
          Entorno de desarrollo
        </span>
        <label className="font-label-md text-label-md text-on-surface-variant flex items-center gap-space-xs">
          Origen
          <select value={source} onChange={(e) => setSource(e.target.value as 'mock' | 'socket')} className={FIELD}>
            <option value="mock">Datos simulados</option>
            <option value="socket">Gateway real (WebSocket)</option>
          </select>
        </label>
      </div>
      {source === 'mock' ? <MockHarness /> : <SocketHarness />}
    </div>
  );
}
