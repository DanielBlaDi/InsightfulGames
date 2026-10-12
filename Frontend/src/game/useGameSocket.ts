import { useCallback } from 'react';
import type { GameSession } from './session';
import { useGameTransport } from './useGameTransport';
import { createWebSocketTransport, gameSocketUrl } from './wsTransport';

interface GameSocketOptions {
  gameId: string; // devuelto por POST /games
  token: string; // accessToken del login
}

/** Sesión de juego sobre el WebSocket del API Gateway. */
export function useGameSocket({ gameId, token }: GameSocketOptions): GameSession {
  const create = useCallback(() => createWebSocketTransport(gameSocketUrl(gameId, token)), [gameId, token]);
  return useGameTransport(create);
}
