import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
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
  // Cambiar el intento vuelve a ejecutar el efecto: cierra la conexión actual y abre una nueva.
  const [attempt, setAttempt] = useState(0);
  // Versión del último `state`: cada jugada la envía como expectedVersion (sección 9).
  const version = useRef<number | null>(null);
  useEffect(() => {
    version.current = view.state?.version ?? null;
  }, [view.state]);

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
  }, [create, attempt]);

  const send = useCallback((message: ClientMessage) => {
    if (!transport.current) return;
    dispatch({ type: 'sent' }); // antes de enviar: el simulador responde de forma síncrona
    transport.current.send(message);
  }, []);

  const sendMove = useCallback(
    (uci: string) => {
      if (version.current === null) return; // sin `state` no hay versión que enviar
      send({ type: 'move', uci, expectedVersion: version.current });
    },
    [send],
  );

  const resign = useCallback(
    (side?: Color) => send(side ? { type: 'resign', side } : { type: 'resign' }),
    [send],
  );

  const reconnect = useCallback(() => setAttempt((n) => n + 1), []);

  return { ...view, sendMove, resign, reconnect };
}
