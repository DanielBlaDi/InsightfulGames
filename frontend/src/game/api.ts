import { apiUrl } from './config';
import { isRecord } from './guards';
import type { CreateGameRequest, GameState } from './types';

/** Error con la forma uniforme del contrato: { "error": { "code", "message" } }. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/**
 * POST /api/games. Devuelve el GameState de la partida creada. La sesión va en la cookie
 * session, que el navegador envía sola; el código no maneja el token (sección 6).
 */
export async function createGame(request: CreateGameRequest, signal?: AbortSignal): Promise<GameState> {
  const response = await fetch(apiUrl('/games'), {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  });
  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const error = isRecord(body) && isRecord(body.error) ? body.error : null;
    throw new ApiError(
      response.status,
      typeof error?.code === 'string' ? error.code : 'UNKNOWN',
      typeof error?.message === 'string' ? error.message : `El servidor respondió con el código ${response.status}.`,
    );
  }
  if (!isRecord(body) || typeof body.gameId !== 'string') {
    throw new ApiError(response.status, 'INVALID_RESPONSE', 'El servidor devolvió una respuesta inesperada.');
  }
  return body as unknown as GameState;
}
