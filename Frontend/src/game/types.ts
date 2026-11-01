// Tipos del contrato v9 (secciones 9 y 19). Si el contrato cambia, este archivo cambia con él.

export type Color = 'white' | 'black';
export type GameMode = 'local' | 'vs_bot' | 'multiplayer';
export type GameStatus = 'waiting' | 'in_progress' | 'finished';
export type GameResult = Color | 'draw';
export type EndReason = 'checkmate' | 'stalemate' | 'surrender' | 'draw' | 'timeout' | 'abandonment' | 'expired';
export type Visibility = 'private' | 'shared';
export type PromotionPiece = 'q' | 'r' | 'b' | 'n';

/** Mapa casilla de origen → casillas de destino. Vacío si la partida terminó. */
export type LegalMoves = Record<string, string[]>;

export interface Participant {
  userId: string;
  color: Color;
}

export interface TimeControl {
  minutes: number;
}

/** Milisegundos de cada color al inicio de su turno; deadline = turnStartedAt + clocks[turn]. */
export interface Clocks {
  white: number | null;
  black: number | null;
  turnStartedAt: string | null;
  deadline: string | null;
}

export interface GameMove {
  ply: number;
  color: Color;
  san: string;
  uci: string;
  fenAfter: string;
  timestamp: string;
}

export interface GameState {
  gameId: string;
  mode: GameMode;
  visibility: Visibility;
  matchId: string | null; // solo multiplayer
  /** local: el creador dos veces, una por color. vs_bot: solo el humano. */
  participants: Participant[];
  botLevel: number | null; // solo vs_bot
  timeControl: TimeControl | null;
  clocks: Clocks | null;
  status: GameStatus;
  turn: Color;
  fen: string;
  initialFen?: string;
  legalMoves: LegalMoves;
  moves: GameMove[];
  drawOffer: Color | null;
  /** Sube con cada cambio. Se envía como expectedVersion en cada jugada. */
  version: number;
  result: GameResult | null;
  endReason: EndReason | null;
  createdAt: string;
  finishedAt: string | null;
}

// POST /api/games (sección 9): botLevel y playerColor solo en vs_bot. Sin timeControl ni
// visibility, la partida no tiene reloj y es privada.
interface CreateGameOptions {
  timeControl?: TimeControl | null;
  visibility?: Visibility;
}

export type CreateGameRequest =
  | ({ mode: 'local' } & CreateGameOptions)
  | ({ mode: 'vs_bot'; botLevel: number; playerColor: Color } & CreateGameOptions);

export const MIN_BOT_LEVEL = 1;
export const MAX_BOT_LEVEL = 20;

// WebSocket /api/ws/games/{id}, con la cookie session (sección 9).

export type ClientMessage =
  | { type: 'move'; uci: string; expectedVersion: number }
  | { type: 'resign'; side?: Color }; // side solo en modo local

export type ServerMessage =
  | { type: 'state'; state: GameState; lastMove?: string }
  | { type: 'move_rejected'; code: string; message: string }
  | { type: 'bot_thinking' }
  | { type: 'game_over'; result: GameResult | null; endReason: EndReason }
  // Fuera de la sección 9 para Single Player (sí existe en Multiplayer): fallos que no son una
  // jugada rechazada, como Botcito o Game Logic no disponibles. No cambia el estado de la partida.
  | { type: 'error'; code: string; message: string };

/** Color del humano en vs_bot: el único participante. null en local y multiplayer. */
export function humanColor(state: GameState): Color | null {
  return state.mode === 'vs_bot' ? (state.participants[0]?.color ?? null) : null;
}
