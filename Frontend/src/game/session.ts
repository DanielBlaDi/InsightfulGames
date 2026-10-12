import type { ClientMessage, Color, GameState, ServerMessage } from './types';

// Costura entre la pantalla y el canal de comunicación. No forma parte del contrato:
// GamePage consume un GameSession y no sabe si detrás hay un simulador o un WebSocket.

export interface MoveRejection {
  code: string;
  message: string;
}

export type ConnectionStatus = 'connecting' | 'open' | 'closed';

/** Códigos de cierre del WebSocket definidos en el contrato (sección 5). */
export const CLOSE_UNAUTHORIZED = 4401;
export const CLOSE_GAME_NOT_FOUND = 4404;

export interface SessionView {
  connection: ConnectionStatus;
  closeCode: number | null; // solo si el servidor o la red cerraron la conexión
  state: GameState | null; // null hasta recibir el primer `state`
  lastMove: string | null;
  botThinking: boolean;
  /** Hay un mensaje enviado sin respuesta: el servidor contestará con `state` o `move_rejected`. */
  awaitingReply: boolean;
  rejection: MoveRejection | null;
}

export interface GameSession extends SessionView {
  sendMove: (uci: string) => void;
  resign: (side?: Color) => void;
}

export interface TransportHandlers {
  onOpen: () => void;
  onMessage: (message: ServerMessage) => void;
  onClose: (code: number) => void;
}

export interface GameTransport {
  connect: (handlers: TransportHandlers) => void;
  send: (message: ClientMessage) => void;
  /** Cierre pedido por el cliente: no dispara onClose. */
  close: () => void;
}

export type SessionEvent =
  | { type: 'connecting' }
  | { type: 'open' }
  | { type: 'sent' }
  | { type: 'closed'; code: number }
  | { type: 'message'; message: ServerMessage };

export const initialSessionView: SessionView = {
  connection: 'connecting',
  closeCode: null,
  state: null,
  lastMove: null,
  botThinking: false,
  awaitingReply: false,
  rejection: null,
};

/** Cada `state` reemplaza al anterior: el frontend solo pinta lo que recibe. */
function applyMessage(view: SessionView, message: ServerMessage): SessionView {
  switch (message.type) {
    case 'state':
      return {
        ...view,
        state: message.state,
        // El `state` inicial llega sin lastMove; se recupera del historial.
        lastMove: message.lastMove ?? message.state.moves.at(-1)?.uci ?? null,
        botThinking: false,
        awaitingReply: false,
        rejection: null,
      };
    case 'move_rejected':
      return { ...view, awaitingReply: false, rejection: { code: message.code, message: message.message } };
    case 'bot_thinking':
      return { ...view, botThinking: true, rejection: null };
    case 'game_over':
      // El `state` previo ya trae status, result y endReason.
      return { ...view, botThinking: false };
    default:
      return view; // tipo de mensaje no contemplado en el contrato
  }
}

export function sessionReducer(view: SessionView, event: SessionEvent): SessionView {
  switch (event.type) {
    case 'connecting':
      return initialSessionView;
    case 'open':
      return { ...view, connection: 'open', closeCode: null };
    case 'sent':
      return { ...view, awaitingReply: true, rejection: null };
    case 'closed':
      return { ...view, connection: 'closed', closeCode: event.code, botThinking: false, awaitingReply: false };
    case 'message':
      return applyMessage(view, event.message);
  }
}
