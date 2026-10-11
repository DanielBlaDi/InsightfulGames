// API pública del módulo de partida. El simulador (./mock) queda fuera a propósito.
export { default as GameScreen } from './GameScreen';
export { default as GamePage } from './GamePage';
export { default as ChessBoard } from './ChessBoard';
export { useGameSocket } from './useGameSocket';
export type { GameSession } from './session';
export type * from './types';
