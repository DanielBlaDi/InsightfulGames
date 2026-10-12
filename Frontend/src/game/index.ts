// API pública del módulo de partida. El simulador (./mock) queda fuera a propósito.

// Flujo completo: configurar, crear (POST /games) y jugar. Es lo que monta la aplicación principal.
export { default as PlayChess } from './PlayChess';

// Piezas sueltas, por si la aplicación quiere componer el flujo de otra forma.
export { default as GameSetup } from './GameSetup';
export { default as GameScreen } from './GameScreen';
export { default as GamePage } from './GamePage';
export { default as ChessBoard } from './ChessBoard';
export { useGameSocket } from './useGameSocket';
export { ApiError, createGame } from './api';
export { gatewayBaseUrl } from './config';

export type { GameSession } from './session';
export { MAX_BOT_LEVEL, MIN_BOT_LEVEL } from './types';
export type * from './types';
