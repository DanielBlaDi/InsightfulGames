import { useState } from 'react';
import GamePage from '../GamePage';
import { SCENARIOS } from './scenarios';
import type { MockScenario } from './scenarios';
import { useMockGame } from './useMockGame';

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

export default function DevHarness() {
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const [run, setRun] = useState(0);
  const scenario = SCENARIOS.find((s) => s.id === scenarioId) ?? SCENARIOS[0];

  return (
    <div className="w-full min-h-screen bg-background">
      <div className="px-gutter-mobile md:px-margin py-space-sm bg-surface-container flex flex-wrap items-center gap-space-sm border-b border-outline-variant/40">
        <span className="px-2 py-0.5 rounded-full bg-tertiary/10 text-tertiary font-label-sm text-label-sm uppercase tracking-wider">
          Datos simulados
        </span>
        <label className="font-label-md text-label-md text-on-surface-variant flex items-center gap-space-xs">
          Escenario
          <select
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
            className="rounded-lg border-outline-variant bg-surface text-on-surface font-body-sm text-body-sm py-1"
          >
            {SCENARIOS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => setRun(run + 1)}
          className="px-space-sm py-1 rounded-lg bg-surface-container-highest text-on-surface font-label-md text-label-md hover:bg-surface-container-high transition-colors cursor-pointer"
        >
          Reiniciar
        </button>
      </div>
      <MockGame key={`${scenario.id}-${run}`} scenario={scenario} />
    </div>
  );
}
