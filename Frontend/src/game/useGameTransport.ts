import { useCallback, useEffect, useReducer, useRef } from 'react';
import { initialSessionView, sessionReducer } from './session';
import type { GameSession, GameTransport } from './session';
import type { ClientMessage, Color } from './types';

/**
 * Mantiene una sesión de juego sobre cualquier transporte (simulado o WebSocket).
 * `create` debe ser estable (useCallback): cada vez que cambia se abre una conexión nueva.
 */
export function useGameTransport(create: () => GameTransport): GameSession {
  const [view, dispatch] = useReducer(sessionReducer, initialSessionView);
  const transport = useRef<GameTransport | null>(null);

  useEffect(() => {
    dispatch({ type: 'connecting' });
    const current = create();
    transport.current = current;
    current.connect({
      onOpen: () => dispatch({ type: 'open' }),
      onMessage: (message) => dispatch({ type: 'message', message }),
      onClose: (code) => dispatch({ type: 'closed', code }),
    });
    return () => {
      current.close();
      transport.current = null;
    };
  }, [create]);

  const send = useCallback((message: ClientMessage) => {
    if (!transport.current) return;
    dispatch({ type: 'sent' }); // antes de enviar: el simulador responde de forma síncrona
    transport.current.send(message);
  }, []);

  const sendMove = useCallback((uci: string) => send({ type: 'move', uci }), [send]);

  const resign = useCallback(
    (side?: Color) => send(side ? { type: 'resign', side } : { type: 'resign' }),
    [send],
  );

  return { ...view, sendMove, resign };
}
