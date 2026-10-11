import { useCallback } from 'react';
import type { GameSession } from '../session';
import { useGameTransport } from '../useGameTransport';
import { createMockTransport } from './mockTransport';
import type { MockScenario } from './scenarios';

/** Sesión de juego respaldada por el simulador. Para reiniciar, volver a montar el componente. */
export function useMockGame(scenario: MockScenario): GameSession {
  const create = useCallback(() => createMockTransport(scenario), [scenario]);
  return useGameTransport(create);
}
