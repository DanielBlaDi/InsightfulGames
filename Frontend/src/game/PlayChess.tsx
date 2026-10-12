import { useCallback } from 'react';
import { createGame } from './api';
import GameFlow from './GameFlow';
import GameScreen from './GameScreen';
import type { CreateGameRequest } from './types';

interface PlayChessProps {
  /** accessToken devuelto por POST /auth/login. Se recibe por props y solo vive en memoria. */
  token: string;
  /** El Gateway rechazó el token (401 en REST o cierre 4401 en el WebSocket): toca volver al login. */
  onUnauthorized?: () => void;
}

/**
 * Punto de entrada para la aplicación principal: configurar una partida, crearla en el
 * Gateway y jugarla. Uso: <PlayChess token={accessToken} onUnauthorized={irAlLogin} />
 */
export default function PlayChess({ token, onUnauthorized }: PlayChessProps) {
  const create = useCallback(
    (request: CreateGameRequest, signal: AbortSignal) => createGame(request, token, signal),
    [token],
  );

  return (
    <GameFlow
      createGame={create}
      onUnauthorized={onUnauthorized}
      renderGame={(game, onExit) => (
        <GameScreen gameId={game.gameId} token={token} onUnauthorized={onUnauthorized} onExit={onExit} />
      )}
    />
  );
}
