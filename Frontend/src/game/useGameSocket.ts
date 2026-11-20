import { useCallback } from 'react';
import type { GameSession } from './session';
import { useGameTransport } from './useGameTransport';
import { createWebSocketTransport, gameSocketUrl } from './wsTransport';

interface GameSocketOptions {
  gameId: string; // devuelto por POST /api/games
}

/** Sesión de juego sobre el WebSocket de Single Player. La identidad va en la cookie session. */
export function useGameSocket({ gameId }: GameSocketOptions): GameSession {
  const create = useCallback(() => createWebSocketTransport(gameSocketUrl(gameId)), [gameId]);
  return useGameTransport(create);
}
