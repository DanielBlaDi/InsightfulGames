import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { apiSocketUrl } from '../game/config';
import { isRecord } from '../game/guards';
import { initialMatchView, matchReducer, reconnectDelay, shouldReconnect } from './matchSession';
import type { MatchView } from './matchSession';
import type { MatchClientMessage, MatchServerMessage } from './types';

const PING_MS = 25_000;

export function matchSocketUrl(matchId: string): string {
  return apiSocketUrl(`/ws/matches/${encodeURIComponent(matchId)}`);
}

const TYPES = new Set([
  'state',
  'move_rejected',
  'game_over',
  'opponent_connected',
  'opponent_disconnected',
  'draw_offered',
  'draw_declined',
  'draw_cancelled',
  'error',
  'pong',
]);

/** Descarta lo que no tenga la forma mínima que la pantalla necesita. */
export function parseMatchMessage(data: unknown): MatchServerMessage | null {
  let message: unknown;
  try {
    message = JSON.parse(String(data));
  } catch {
    return null;
  }
  if (!isRecord(message) || typeof message.type !== 'string' || !TYPES.has(message.type)) return null;
  if (message.type === 'state') {
    const s = message.state;
    const ok =
      isRecord(s) &&
      typeof s.gameId === 'string' &&
      typeof s.fen === 'string' &&
      typeof s.status === 'string' &&
      typeof s.version === 'number' &&
      Array.isArray(s.participants) &&
      Array.isArray(s.moves);
    if (!ok) return null;
    // Una partida en espera puede no traer legalMoves: el tablero necesita al menos un objeto vacío.
    if (!isRecord(s.legalMoves)) s.legalMoves = {};
  }
  if ((message.type === 'move_rejected' || message.type === 'error') && typeof message.code !== 'string') return null;
  return message as unknown as MatchServerMessage;
}

export interface MatchSession extends MatchView {
  sendMove: (uci: string) => void;
  send: (message: Exclude<MatchClientMessage, { type: 'move' }>) => void;
  /** Reconexión manual (tras agotar los reintentos automáticos o un cierre no recuperable). */
  reconnect: () => void;
}

/**
 * Conexión a /api/ws/matches/{matchId} con la cookie de sesión. El servidor manda el `state`
 * vigente al conectar, así que reconectar nunca reenvía jugadas: solo vuelve a escuchar.
 */
export function useMatchSocket(matchId: string | null): MatchSession {
  const [view, dispatch] = useReducer(matchReducer, initialMatchView);
  const socketRef = useRef<WebSocket | null>(null);
  const viewRef = useRef(view);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    viewRef.current = view;
  }, [view]);

  useEffect(() => {
    if (!matchId) return;
    let disposed = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let pingTimer: ReturnType<typeof setInterval> | undefined;

    const open = () => {
      if (disposed) return;
      dispatch({ type: 'connecting' });
      let ws: WebSocket;
      try {
        ws = new WebSocket(matchSocketUrl(matchId));
      } catch {
        dispatch({ type: 'closed', code: 1006, reason: '', willRetry: false });
        return;
      }
      socketRef.current = ws;
      ws.onopen = () => {
        dispatch({ type: 'open' });
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
        }, PING_MS);
      };
      ws.onmessage = (event) => {
        const message = parseMatchMessage(event.data);
        if (message) dispatch({ type: 'message', message });
      };
      ws.onclose = (event) => {
        clearInterval(pingTimer);
        if (disposed) return;
        socketRef.current = null;
        const current = viewRef.current;
        const finished = current.state?.status === 'finished' || current.gameOver !== null;
        const retry = shouldReconnect(event.code, finished, current.retries);
        dispatch({ type: 'closed', code: event.code, reason: event.reason, willRetry: retry });
        if (retry) retryTimer = setTimeout(open, reconnectDelay(current.retries));
      };
    };

    open();
    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      clearInterval(pingTimer);
      const ws = socketRef.current;
      socketRef.current = null;
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onclose = null;
        ws.close(1000);
      }
    };
  }, [matchId, attempt]);

  const sendRaw = useCallback((message: MatchClientMessage) => {
    const ws = socketRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(message));
    return true;
  }, []);

  const sendMove = useCallback(
    (uci: string) => {
      const current = viewRef.current;
      // Una sola jugada en vuelo, siempre con la versión del último state recibido.
      if (current.awaitingReply || !current.state) return;
      dispatch({ type: 'sent' });
      if (!sendRaw({ type: 'move', uci, expectedVersion: current.state.version })) {
        dispatch({ type: 'message', message: { type: 'error', code: 'NOT_CONNECTED', message: 'Sin conexión con la partida.' } });
      }
    },
    [sendRaw],
  );

  const send = useCallback(
    (message: Exclude<MatchClientMessage, { type: 'move' }>) => {
      if (viewRef.current.awaitingReply) return;
      dispatch({ type: 'sent' });
      if (!sendRaw(message)) {
        dispatch({ type: 'message', message: { type: 'error', code: 'NOT_CONNECTED', message: 'Sin conexión con la partida.' } });
      }
    },
    [sendRaw],
  );

  // Si el servidor no contesta una acción en 10 s, se desbloquea la pantalla (el próximo state manda).
  useEffect(() => {
    if (!view.awaitingReply) return;
    const timer = setTimeout(() => {
      dispatch({
        type: 'message',
        message: { type: 'error', code: 'NO_REPLY', message: 'El servidor no respondió. Revisa la jugada e inténtalo de nuevo.' },
      });
    }, 10_000);
    return () => clearTimeout(timer);
  }, [view.awaitingReply]);

  const reconnect = useCallback(() => setAttempt((n) => n + 1), []);

  return { ...view, sendMove, send, reconnect };
}
