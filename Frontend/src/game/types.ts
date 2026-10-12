// Tipos del contrato oficial (contracts.docx, secciones 4 y 5).
// Si el contrato cambia, este archivo cambia con él.

export type Color = 'white' | 'black';
export type GameMode = 'local' | 'vs_bot';
export type GameStatus = 'in_progress' | 'finished';
export type GameResult = Color | 'draw';
export type EndReason = 'checkmate' | 'stalemate' | 'resignation' | 'draw';
export type PromotionPiece = 'q' | 'r' | 'b' | 'n';

/** Mapa casilla de origen → casillas de destino. Vacío si la partida terminó. */
export type LegalMoves = Record<string, string[]>;

export interface GameMove {
  ply: number;
  san: string;
  uci: string;
  fenAfter: string;
  timestamp: string;
}

export interface GameState {
  gameId: string;
  userId: string;
  mode: GameMode;
  botLevel: number | null; // solo vs_bot
  playerColor: Color | null; // solo vs_bot
  status: GameStatus;
  turn: Color;
  fen: string;
  legalMoves: LegalMoves;
  moves: GameMove[];
  result: GameResult | null;
  endReason: EndReason | null;
  createdAt: string;
  finishedAt: string | null;
}

// POST /games (sección 3.4): level y playerColor solo se envían en vs_bot.
export type CreateGameRequest =
  | { mode: 'local' }
  | { mode: 'vs_bot'; level: number; playerColor: Color };

export const MIN_BOT_LEVEL = 1;
export const MAX_BOT_LEVEL = 20;

// WebSocket /ws/games/{id}?token=<jwt>

export type ClientMessage =
  | { type: 'move'; uci: string }
  | { type: 'resign'; side?: Color }; // side solo en modo local

export type ServerMessage =
  | { type: 'state'; state: GameState; lastMove?: string }
  | { type: 'move_rejected'; code: string; message: string }
  | { type: 'bot_thinking' }
  | { type: 'game_over'; result: GameResult; endReason: EndReason };
