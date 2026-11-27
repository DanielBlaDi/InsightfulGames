// Estado de la conexión de una partida multijugador. Lógica pura (sin React ni WebSocket) para
// poder probarla: el servidor es la fuente de verdad y cada `state` reemplaza al anterior.
import type { Clocks, Color, EndReason, GameResult, GameState } from '../game/types';
import type { MatchServerMessage } from './types';

export type MatchConnection = 'connecting' | 'open' | 'reconnecting' | 'closed';

export interface Notice {
  code: string;
  message: string;
}

export interface MatchView {
  connection: MatchConnection;
  /** Código del último cierre que no se va a reintentar solo (4401, 4404, 4403, 1000 por otra pestaña…). */
  closeCode: number | null;
  closeReason: string | null;
  /** Intentos de reconexión automática seguidos (se reinicia al abrir). */
  retries: number;
  state: GameState | null;
  lastMove: string | null;
  /** Hay una jugada o acción enviada sin respuesta: no se envía otra. */
  awaitingReply: boolean;
  rejection: Notice | null;
  serverError: Notice | null;
  /** null = desconocido (el servidor solo avisa cuando el rival se conecta o se desconecta). */
  opponentOnline: boolean | null;
  opponentDeadline: string | null;
  drawNotice: 'declined' | 'cancelled' | null;
  gameOver: { result: GameResult | null; endReason: EndReason | null } | null;
  /**
   * userId del único participante visto mientras la partida esperaba rival. El WebSocket solo acepta
   * participantes, así que en ese momento solo puede ser quien está conectado (el creador). Sirve
   * de respaldo si el perfil no está disponible; nunca se inventa.
   */
  waitingCreator: string | null;
}

export type MatchEvent =
  | { type: 'connecting' }
  | { type: 'open' }
  | { type: 'sent' }
  | { type: 'closed'; code: number; reason: string; willRetry: boolean }
  | { type: 'message'; message: MatchServerMessage };

export const initialMatchView: MatchView = {
  connection: 'connecting',
  closeCode: null,
  closeReason: null,
  retries: 0,
  state: null,
  lastMove: null,
  awaitingReply: false,
  rejection: null,
  serverError: null,
  opponentOnline: null,
  opponentDeadline: null,
  drawNotice: null,
  gameOver: null,
  waitingCreator: null,
};

function applyMessage(view: MatchView, message: MatchServerMessage): MatchView {
  switch (message.type) {
    case 'state': {
      const next = message.state;
      // Un state más viejo que el que ya se pinta (misma partida) no puede deshacer el tablero.
      if (view.state && view.state.gameId === next.gameId && next.version < view.state.version) return view;
      return {
        ...view,
        state: next,
        lastMove: message.lastMove ?? next.moves.at(-1)?.uci ?? null,
        awaitingReply: false,
        rejection: null,
        serverError: null,
        drawNotice: next.drawOffer ? null : view.drawNotice,
        gameOver: next.status === 'finished' ? { result: next.result, endReason: next.endReason } : view.gameOver,
        waitingCreator:
          view.waitingCreator ??
          (next.status === 'waiting' && next.participants.length === 1 ? next.participants[0].userId : null),
      };
    }
    case 'move_rejected':
      return { ...view, awaitingReply: false, rejection: { code: message.code, message: message.message } };
    case 'error':
      return { ...view, awaitingReply: false, serverError: { code: message.code, message: message.message } };
    case 'game_over':
      return { ...view, awaitingReply: false, gameOver: { result: message.result, endReason: message.endReason } };
    case 'opponent_connected':
      return { ...view, opponentOnline: true, opponentDeadline: null };
    case 'opponent_disconnected':
      return { ...view, opponentOnline: false, opponentDeadline: message.reconnectDeadline };
    case 'draw_offered':
      return { ...view, awaitingReply: false, drawNotice: null };
    case 'draw_declined':
      return { ...view, awaitingReply: false, drawNotice: 'declined' };
    case 'draw_cancelled':
      return { ...view, awaitingReply: false, drawNotice: 'cancelled' };
    case 'pong':
    default:
      return view;
  }
}

export function matchReducer(view: MatchView, event: MatchEvent): MatchView {
  switch (event.type) {
    case 'connecting':
      // Se conserva el último state: al reconectar el tablero no desaparece; el servidor manda el vigente.
      return { ...view, connection: view.state ? 'reconnecting' : 'connecting', awaitingReply: false };
    case 'open':
      return { ...view, connection: 'open', closeCode: null, closeReason: null, retries: 0 };
    case 'sent':
      return { ...view, awaitingReply: true, rejection: null, serverError: null, drawNotice: null };
    case 'closed':
      return {
        ...view,
        connection: event.willRetry ? 'reconnecting' : 'closed',
        closeCode: event.willRetry ? null : event.code,
        closeReason: event.willRetry ? null : event.reason,
        retries: event.willRetry ? view.retries + 1 : view.retries,
        awaitingReply: false,
      };
    case 'message':
      return applyMessage(view, event.message);
  }
}

export const CLOSE_NORMAL = 1000;
export const CLOSE_UNAUTHORIZED = 4401;
export const CLOSE_FORBIDDEN_ORIGIN = 4403;
export const CLOSE_NOT_FOUND = 4404;
export const MAX_RETRIES = 8;

/**
 * ¿Reconectar solo? No ante sesión inválida, origen prohibido, partida ajena, fin normal de la
 * partida ni cuando otra pestaña tomó la conexión (1000 "reconnected"). Sí ante cortes de red,
 * reinicios del servidor (1001, 1006, 1011, 1012…).
 */
export function shouldReconnect(code: number, finished: boolean, retries: number): boolean {
  if (finished || retries >= MAX_RETRIES) return false;
  if (code === CLOSE_NORMAL || code === CLOSE_UNAUTHORIZED || code === CLOSE_FORBIDDEN_ORIGIN || code === CLOSE_NOT_FOUND) {
    return false;
  }
  return true;
}

/** Espera antes del reintento n (1, 2, 4, 8 s… hasta 10 s). */
export const reconnectDelay = (retries: number) => Math.min(10_000, 1000 * 2 ** retries);

/** ¿Puede este usuario mover ahora? Solo con la partida en curso, su turno y nada pendiente. */
export function canMove(view: MatchView, myColor: Color | null): boolean {
  const s = view.state;
  return (
    !!s &&
    !!myColor &&
    s.status === 'in_progress' &&
    !view.gameOver &&
    s.turn === myColor &&
    view.connection === 'open' &&
    !view.awaitingReply
  );
}

/**
 * Milisegundos que le quedan a `color` según el servidor. Solo se descuenta el tiempo del bando que
 * tiene el turno, a partir de `deadline` (o de `turnStartedAt`). Nunca baja de 0 y no decide nada:
 * quien declara la derrota por tiempo es el servidor.
 */
export function remainingMs(clocks: Clocks | null, turn: Color, status: string, color: Color, now: number): number | null {
  if (!clocks) return null;
  const base = clocks[color];
  if (base === null || base === undefined) return null;
  if (status !== 'in_progress' || color !== turn) return Math.max(0, base);
  if (clocks.deadline) {
    const deadline = Date.parse(clocks.deadline);
    if (!Number.isNaN(deadline)) return Math.max(0, deadline - now);
  }
  if (clocks.turnStartedAt) {
    const started = Date.parse(clocks.turnStartedAt);
    if (!Number.isNaN(started)) return Math.max(0, base - (now - started));
  }
  return Math.max(0, base);
}

export function formatClock(ms: number | null): string {
  if (ms === null) return '--:--';
  const total = Math.ceil(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}
