import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ApiError } from './api';
import GameSetup from './GameSetup';
import type { CreateGameRequest, GameState } from './types';

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.status === 401 ? 'Tu sesión venció. Inicia sesión de nuevo.' : error.message;
  }
  return 'No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo.';
}

interface GameFlowProps {
  /** Crea la partida (POST /games). Si falla, el error se muestra: nunca se sustituye por datos simulados. */
  createGame: (request: CreateGameRequest, signal: AbortSignal) => Promise<GameState>;
  /** Pinta la partida creada; `onExit` devuelve a la configuración. */
  renderGame: (game: GameState, onExit: () => void) => ReactNode;
  onUnauthorized?: () => void;
  /** Salir del módulo desde la configuración. */
  onExit?: () => void;
}

/** Configuración → creación → partida. No sabe de dónde salen las partidas ni cómo se juegan. */
export default function GameFlow({ createGame, renderGame, onUnauthorized, onExit }: GameFlowProps) {
  const [game, setGame] = useState<GameState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<AbortController | null>(null);

  useEffect(() => () => pending.current?.abort(), []);

  const handleStart = async (request: CreateGameRequest) => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setLoading(true);
    setError(null);
    try {
      const created = await createGame(request, controller.signal);
      if (controller.signal.aborted) return;
      setGame(created);
    } catch (cause) {
      if (controller.signal.aborted) return;
      setError(describeError(cause));
      if (cause instanceof ApiError && cause.status === 401) onUnauthorized?.();
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setLoading(false);
      }
    }
  };

  if (game) return renderGame(game, () => setGame(null));
  return <GameSetup loading={loading} error={error} onStart={handleStart} onExit={onExit} />;
}
