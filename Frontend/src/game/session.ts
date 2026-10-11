import type { ClientMessage, Color, GameState, ServerMessage } from './types';

// Costura entre la pantalla y el canal de comunicación. No forma parte del contrato:
// GamePage consume un GameSession y no sabe si detrás hay un simulador o un WebSocket.

export interface MoveRejection {
  code: string;
  message: string;
}

export interface SessionView {
  state: GameState | null; // null hasta recibir el primer `state`
  lastMove: string | null;
  botThinking: boolean;
  rejection: MoveRejection | null;
}

export interface GameSession extends SessionView {
  sendMove: (uci: string) => void;
  resign: (side?: Color) => void;
}

export interface GameTransport {
  connect: (onMessage: (message: ServerMessage) => void) => void;
  send: (message: ClientMessage) => void;
  close: () => void;
}

export const initialSessionView: SessionView = {
  state: null,
  lastMove: null,
  botThinking: false,
  rejection: null,
};

/** Cada `state` reemplaza al anterior: el frontend solo pinta lo que recibe. */
export function sessionReducer(view: SessionView, message: ServerMessage): SessionView {
  switch (message.type) {
    case 'state':
      return {
        state: message.state,
        // El `state` inicial llega sin lastMove; se recupera del historial.
        lastMove: message.lastMove ?? message.state.moves.at(-1)?.uci ?? null,
        botThinking: false,
        rejection: null,
      };
    case 'move_rejected':
      return { ...view, rejection: { code: message.code, message: message.message } };
    case 'bot_thinking':
      return { ...view, botThinking: true, rejection: null };
    case 'game_over':
      // El `state` previo ya trae status, result y endReason.
      return { ...view, botThinking: false };
  }
}
