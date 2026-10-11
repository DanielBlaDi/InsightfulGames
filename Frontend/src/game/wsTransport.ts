import type { GameTransport } from './session';
import type { ServerMessage } from './types';

const CLOSE_ABNORMAL = 1006;

/**
 * URL del WebSocket de una partida: /ws/games/{id}?token=<jwt>, siempre en el API Gateway.
 * La base sale de VITE_WS_URL (p. ej. ws://localhost:8080; también admite http/https);
 * si no está definida se usa el mismo host que sirve el frontend.
 * El contrato exige el token en la URL del socket: no registrar esta cadena en consola ni en logs.
 */
export function gameSocketUrl(gameId: string, token: string): string {
  const configured: string | undefined = import.meta.env.VITE_WS_URL;
  const base = configured
    ? configured.replace(/\/+$/, '').replace(/^http/i, 'ws')
    : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
  return `${base}/ws/games/${encodeURIComponent(gameId)}?token=${encodeURIComponent(token)}`;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

/** Descarta lo que no tenga la forma mínima que la pantalla necesita para no romperse. */
function parseServerMessage(data: unknown): ServerMessage | null {
  let message: unknown;
  try {
    message = JSON.parse(String(data));
  } catch {
    return null;
  }
  if (!isRecord(message)) return null;

  switch (message.type) {
    case 'state': {
      const { state } = message;
      const valid =
        isRecord(state) &&
        typeof state.fen === 'string' &&
        isRecord(state.legalMoves) &&
        Array.isArray(state.moves);
      return valid ? (message as ServerMessage) : null;
    }
    case 'move_rejected':
      return typeof message.code === 'string' && typeof message.message === 'string'
        ? (message as ServerMessage)
        : null;
    case 'bot_thinking':
    case 'game_over':
      return message as ServerMessage;
    default:
      return null;
  }
}

export function createWebSocketTransport(url: string): GameTransport {
  let socket: WebSocket | null = null;

  return {
    connect({ onOpen, onMessage, onClose }) {
      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
      } catch {
        onClose(CLOSE_ABNORMAL); // URL base mal configurada
        return;
      }
      socket = ws;
      ws.onopen = onOpen;
      ws.onmessage = (event) => {
        const message = parseServerMessage(event.data);
        if (message) onMessage(message);
      };
      ws.onclose = (event) => onClose(event.code);
    },
    send(message) {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
    },
    close() {
      if (!socket) return;
      socket.onopen = null;
      socket.onmessage = null;
      socket.onclose = null;
      socket.close();
      socket = null;
    },
  };
}
