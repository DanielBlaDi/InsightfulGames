// Multijugador online (contrato técnico definitivo, sección 10; servicio Backend/multiplayer-component).
// El GameState es el mismo de Single Player; aquí van solo los mensajes y cuerpos propios.
import type { Color, EndReason, GameResult, GameState, Visibility } from '../game/types';

export const MIN_MINUTES = 1;
export const MAX_MINUTES = 10;

/** POST /api/matches (con cabecera Idempotency-Key). */
export interface CreateMatchRequest {
  creatorColor: Color;
  timeControl: { minutes: number };
  visibility: Visibility;
}

/** Respuesta 201 (o 201 con Idempotency-Replayed: true al repetir la clave). No trae gameId. */
export interface CreatedMatch {
  matchId: string;
  status: string;
  createdAt: string;
}

/** Mensajes cliente -> servidor por /api/ws/matches/{matchId}. */
export type MatchClientMessage =
  | { type: 'move'; uci: string; expectedVersion: number }
  | { type: 'resign' }
  | { type: 'draw_offer' }
  | { type: 'draw_accept' }
  | { type: 'draw_decline' }
  | { type: 'draw_cancel' }
  | { type: 'ping' };

/** Mensajes servidor -> cliente (internal/service/service.go y internal/httpapi/http.go). */
export type MatchServerMessage =
  | { type: 'state'; state: GameState; lastMove?: string }
  | { type: 'move_rejected'; code: string; message: string }
  | { type: 'game_over'; result: GameResult | null; endReason: EndReason | null }
  | { type: 'opponent_connected' }
  | { type: 'opponent_disconnected'; reconnectDeadline: string | null }
  | { type: 'draw_offered'; by: Color }
  | { type: 'draw_declined' }
  | { type: 'draw_cancelled' }
  | { type: 'error'; code: string; message: string }
  | { type: 'pong' };

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const isMatchId = (value: unknown): value is string => typeof value === 'string' && UUID_RE.test(value);

export const matchPath = (matchId: string) => `/partida/${matchId}`;
export const invitePath = (matchId: string) => `/unirse/${matchId}`;

/** Color del usuario según participants. null si no participa (o aún no se sabe quién es). */
export function colorOf(state: GameState, userId: string | null): Color | null {
  if (!userId) return null;
  return state.participants.find((p) => p.userId === userId)?.color ?? null;
}

export const opposite = (color: Color): Color => (color === 'white' ? 'black' : 'white');
