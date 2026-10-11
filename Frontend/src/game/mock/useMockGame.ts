import { useCallback, useEffect, useReducer, useRef } from 'react';
import { initialSessionView, sessionReducer } from '../session';
import type { GameSession, GameTransport } from '../session';
import type { Color } from '../types';
import { createMockTransport } from './mockTransport';
import type { MockScenario } from './scenarios';

/** Sesión de juego respaldada por el simulador. Para reiniciar, volver a montar el componente. */
export function useMockGame(scenario: MockScenario): GameSession {
  const [view, dispatch] = useReducer(sessionReducer, initialSessionView);
  const transport = useRef<GameTransport | null>(null);

  useEffect(() => {
    const current = createMockTransport(scenario);
    transport.current = current;
    current.connect(dispatch);
    return () => {
      current.close();
      transport.current = null;
    };
  }, [scenario]);

  const sendMove = useCallback((uci: string) => {
    transport.current?.send({ type: 'move', uci });
  }, []);

  const resign = useCallback((side?: Color) => {
    transport.current?.send(side ? { type: 'resign', side } : { type: 'resign' });
  }, []);

  return { ...view, sendMove, resign };
}
