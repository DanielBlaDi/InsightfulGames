import { ApiError } from '../api';
import type { CreateGameRequest, GameState } from '../types';
import { createMockTransport } from './mockTransport';
import { SCENARIO_FOR } from './scenarios';
import type { MockScenario } from './scenarios';

// Sustituto de POST /games para desarrollo. Solo se usa cuando se elige a propósito en el
// arnés de /game.html: nunca como respaldo de una llamada real que haya fallado.

const CREATE_DELAY_MS = 700;

/** Respuestas que el simulador puede dar a POST /games. */
export type MockCreateOutcome = 'ok' | 'validation' | 'unauthorized' | 'offline';

const games = new Map<string, MockScenario>();
let nextGame = 1;

export function mockScenarioOf(gameId: string): MockScenario | undefined {
  return games.get(gameId);
}

const wait = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const id = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => {
      clearTimeout(id);
      reject(new DOMException('Aborted', 'AbortError'));
    });
  });

/** El estado inicial lo da el propio simulador de partidas, igual que hará al conectarse. */
const initialState = (scenario: MockScenario, gameId: string) =>
  new Promise<GameState>((resolve) => {
    const transport = createMockTransport(scenario, gameId);
    transport.connect({
      onOpen: () => {},
      onClose: () => {},
      onMessage: (message) => {
        if (message.type !== 'state') return;
        transport.close();
        resolve(message.state);
      },
    });
  });

export async function mockCreateGame(
  request: CreateGameRequest,
  signal: AbortSignal,
  outcome: MockCreateOutcome = 'ok',
): Promise<GameState> {
  await wait(CREATE_DELAY_MS, signal);

  if (outcome === 'offline') throw new TypeError('Failed to fetch');
  if (outcome === 'unauthorized') throw new ApiError(401, 'UNAUTHORIZED', 'Token ausente, inválido o vencido.');
  if (outcome === 'validation') {
    throw new ApiError(400, 'VALIDATION_ERROR', 'Simulación: campos faltantes o con formato inválido.');
  }

  const base = request.mode === 'local' ? SCENARIO_FOR.local : SCENARIO_FOR[request.playerColor];
  const scenario: MockScenario = request.mode === 'vs_bot' ? { ...base, botLevel: request.level } : base;
  const gameId = `mock-${nextGame++}`;
  games.set(gameId, scenario);
  return initialState(scenario, gameId);
}
