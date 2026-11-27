import { useCallback } from 'react';
import { createGame } from './api';
import GameFlow from './GameFlow';
import GameScreen from './GameScreen';
import type { CreateGameRequest } from './types';

interface PlayChessProps {
  /**
   * Obsoleto con v9: la sesión viaja en la cookie session y el módulo ya no usa el token.
   * Se acepta y se ignora hasta que App.tsx (Frontend A) deje de pasarlo.
   */
  token?: string;
  /** El Gateway rechazó el token (401 en REST o cierre 4401 en el WebSocket): toca volver al login. */
  onUnauthorized?: () => void;
  /** Salir del ajedrez desde la configuración. No cierra la sesión ni abandona ninguna partida. */
  onExit?: () => void;
}

/**
 * Punto de entrada para la aplicación principal: configurar una partida, crearla en el
 * Gateway y jugarla. Uso: <PlayChess onUnauthorized={irAlLogin} onExit={irAlInicio} />
 */
export default function PlayChess({ onUnauthorized, onExit }: PlayChessProps) {
  const create = useCallback(
    (request: CreateGameRequest, signal: AbortSignal) => createGame(request, signal),
    [],
  );

  return (
    <GameFlow
      createGame={create}
      onUnauthorized={onUnauthorized}
      onExit={onExit}
      renderGame={(game, onExit) => (
        <GameScreen gameId={game.gameId} onUnauthorized={onUnauthorized} onExit={onExit} />
      )}
    />
  );
}
