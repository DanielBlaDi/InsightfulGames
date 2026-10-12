import { useState } from 'react';
import type { FormEvent } from 'react';
import GameFlow from '../GameFlow';
import GamePage from '../GamePage';
import PlayChess from '../PlayChess';
import { mockCreateGame, mockScenarioOf } from './mockBackend';
import type { MockCreateOutcome } from './mockBackend';
import { SCENARIOS } from './scenarios';
import type { MockScenario } from './scenarios';
import { useMockGame } from './useMockGame';

const BAR =
  'px-gutter-mobile md:px-margin py-space-sm bg-surface-container flex flex-wrap items-center gap-space-sm border-b border-outline-variant/40';
const FIELD = 'rounded-lg border-outline-variant bg-surface text-on-surface font-body-sm text-body-sm py-1';
const LABEL = 'font-label-md text-label-md text-on-surface-variant flex items-center gap-space-xs';
const BUTTON =
  'px-space-sm py-1 rounded-lg bg-surface-container-highest text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors cursor-pointer';

interface MockGameProps {
  scenario: MockScenario;
  gameId?: string;
  onExit?: () => void;
}

function MockGame({ scenario, gameId, onExit }: MockGameProps) {
  const session = useMockGame(scenario, gameId);
  const played = session.state?.moves.length ?? 0;
  const next = scenario.plies[played];
  const finished = session.state?.status === 'finished';

  return (
    <>
      <p className="px-gutter-mobile md:px-margin pt-space-xs font-body-sm text-body-sm text-on-surface-variant">
        {finished
          ? 'Partida terminada.'
          : next
            ? `Siguiente jugada del guion: ${next.uci.slice(0, 2)} → ${next.uci.slice(2, 4)}${
                next.promotes ? ' (elige pieza)' : ''
              }${next.by === 'bot' ? ' · la hace Botcito' : ''}`
            : 'Fin del guion: cualquier jugada será rechazada por el simulador.'}
      </p>
      <GamePage session={session} onExit={onExit} />
    </>
  );
}

/** Flujo completo sin backend: POST /games y la partida los responde el simulador. */
function MockFlowHarness() {
  const [outcome, setOutcome] = useState<MockCreateOutcome>('ok');
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <>
      <div className={BAR}>
        <label className={LABEL}>
          Respuesta de POST /games
          <select
            value={outcome}
            onChange={(e) => {
              setOutcome(e.target.value as MockCreateOutcome);
              setNotice(null);
            }}
            className={FIELD}
          >
            <option value="ok">201 · partida creada</option>
            <option value="validation">400 · VALIDATION_ERROR</option>
            <option value="unauthorized">401 · UNAUTHORIZED</option>
            <option value="offline">Sin conexión</option>
          </select>
        </label>
        {notice && <span className="font-body-sm text-body-sm text-error">{notice}</span>}
      </div>
      <GameFlow
        createGame={(request, signal) => mockCreateGame(request, signal, outcome)}
        onUnauthorized={() => setNotice('Se llamó a onUnauthorized: aquí la aplicación volvería al login.')}
        renderGame={(game, onExit) => {
          const scenario = mockScenarioOf(game.gameId);
          return scenario ? <MockGame scenario={scenario} gameId={game.gameId} onExit={onExit} /> : null;
        }}
      />
    </>
  );
}

function ScenarioHarness() {
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const [run, setRun] = useState(0);
  const scenario = SCENARIOS.find((s) => s.id === scenarioId) ?? SCENARIOS[0];

  return (
    <>
      <div className={BAR}>
        <label className={LABEL}>
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
 * Prueba contra el Gateway real con el mismo componente que usará la aplicación (PlayChess).
 * El token se escribe aquí y vive solo en memoria: no pasa por la URL de la página ni se guarda.
 */
function GatewayHarness() {
  const [token, setToken] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = String(new FormData(event.currentTarget).get('token') ?? '').trim();
    if (!value) return;
    setNotice(null);
    setToken(value);
  };

  if (token) {
    return (
      <>
        <div className={BAR}>
          <span className="font-body-sm text-body-sm text-on-surface-variant">Sesión iniciada con el token indicado.</span>
          <button type="button" onClick={() => setToken(null)} className={BUTTON}>
            Olvidar token
          </button>
        </div>
        <PlayChess
          token={token}
          onUnauthorized={() => {
            setToken(null);
            setNotice('El Gateway rechazó el token. Aquí la aplicación volvería al login.');
          }}
        />
      </>
    );
  }

  return (
    <form onSubmit={handleSubmit} autoComplete="off" className={BAR}>
      <label className={LABEL}>
        Token (accessToken del login)
        <input name="token" type="password" required autoComplete="off" className={`${FIELD} w-72`} />
      </label>
      <button type="submit" className={BUTTON}>
        Usar token
      </button>
      {notice && <span className="font-body-sm text-body-sm text-error">{notice}</span>}
    </form>
  );
}

type Source = 'flow' | 'scenarios' | 'gateway';

export default function DevHarness() {
  const [source, setSource] = useState<Source>('flow');

  return (
    <div className="w-full min-h-screen bg-background">
      <div className={BAR}>
        <span className="px-2 py-0.5 rounded-full bg-tertiary/10 text-tertiary font-label-sm text-label-sm uppercase tracking-wider">
          Entorno de desarrollo
        </span>
        <label className={LABEL}>
          Origen
          <select value={source} onChange={(e) => setSource(e.target.value as Source)} className={FIELD}>
            <option value="flow">Simulado · flujo completo</option>
            <option value="scenarios">Simulado · escenarios del tablero</option>
            <option value="gateway">Gateway real (REST + WebSocket)</option>
          </select>
        </label>
        {source !== 'gateway' && (
          <span className="font-body-sm text-body-sm text-on-surface-variant">
            Sin backend: las respuestas las da el simulador.
          </span>
        )}
      </div>
      {source === 'flow' && <MockFlowHarness />}
      {source === 'scenarios' && <ScenarioHarness />}
      {source === 'gateway' && <GatewayHarness />}
    </div>
  );
}
