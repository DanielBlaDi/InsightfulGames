import type { Color, EndReason, GameMode, GameResult, GameStatus } from '../game/types';

/** Resumen de una partida según el contrato técnico definitivo (secciones 4.2 y 11.4.1). */
export interface GameSummary {
  gameId: string;
  mode: GameMode;
  status: GameStatus;
  result: GameResult | null;
  createdAt: string;
  matchId?: string | null;
  endReason?: EndReason | null;
  color?: Color | null;
}

/** Paginación uniforme definitiva (sección 4.2). */
export interface GamesPage {
  items: GameSummary[];
  nextCursor: string | null;
}

export type HistoryFilter = 'all' | 'finished' | 'in_progress' | 'waiting';

