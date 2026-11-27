import { apiSocketUrl } from './config';
import { isRecord } from './guards';
import type { GameTransport } from './session';
import type { ServerMessage } from './types';

const CLOSE_ABNORMAL = 1006;

/**
 * URL del WebSocket de una partida: /api/ws/games/{id} en el mismo origen. El navegador envía
 * la cookie session y el gateway valida el token y el Origin antes de aceptar (sección 9).
 */
export function gameSocketUrl(gameId: string): string {
  return apiSocketUrl(`/ws/games/${encodeURIComponent(gameId)}`);
}

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
        Array.isArray(state.moves) &&
        typeof state.version === 'number';
      return valid ? (message as ServerMessage) : null;
    }
    case 'move_rejected':
    case 'error':
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
