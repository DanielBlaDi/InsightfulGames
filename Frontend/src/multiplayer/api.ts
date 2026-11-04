// REST del multijugador por el gateway web (/api/matches). La sesión va sola en la cookie.
import type { GameState } from '../game/types';
import type { CreateMatchRequest, CreatedMatch } from './types';

type FetchFn = typeof fetch;

export interface MatchApiError {
  status: number; // 0 = sin red
  code: string;
  message: string;
}

export type ApiResult<T> = { ok: true; value: T; replayed?: boolean } | { ok: false; error: MatchApiError };

/** Mensajes en español para los códigos que puede devolver el gateway (contrato, sección 20). */
const MESSAGES: Record<string, string> = {
  UNAUTHORIZED: 'Tu sesión venció. Inicia sesión de nuevo.',
  MATCH_NOT_FOUND: 'La partida no existe o ya no está disponible.',
  MATCH_NOT_WAITING: 'La partida ya tiene dos jugadores o terminó.',
  ALREADY_PARTICIPANT: 'Eres el creador de esta partida: no puedes unirte a ti mismo.',
  IDEMPOTENCY_KEY_REUSED: 'Se repitió una solicitud con datos distintos. Vuelve a intentarlo.',
  VALIDATION_ERROR: 'Los datos de la partida no son válidos.',
  SERVICES_UNAVAILABLE: 'El servicio de partidas no responde. Inténtalo de nuevo en unos segundos.',
  NETWORK: 'No hay conexión con el servidor. Revisa tu red e inténtalo de nuevo.',
};

export const describeError = (error: MatchApiError) => MESSAGES[error.code] ?? error.message ?? MESSAGES.SERVICES_UNAVAILABLE;

/** Clave única por operación de creación (Idempotency-Key). Se reutiliza al reintentar la misma creación. */
export function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

async function call<T>(fetchFn: FetchFn, url: string, init: RequestInit): Promise<ApiResult<T>> {
  let res: Response;
  try {
    res = await fetchFn(url, { credentials: 'same-origin', ...init });
  } catch {
    return { ok: false, error: { status: 0, code: 'NETWORK', message: MESSAGES.NETWORK } };
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (body as { error?: { code?: unknown; message?: unknown } } | null)?.error;
    return {
      ok: false,
      error: {
        status: res.status,
        code: typeof err?.code === 'string' ? err.code : res.status === 401 ? 'UNAUTHORIZED' : 'SERVICES_UNAVAILABLE',
        message: typeof err?.message === 'string' ? err.message : '',
      },
    };
  }
  return { ok: true, value: body as T, replayed: res.headers.get('Idempotency-Replayed') === 'true' };
}

/** POST /api/matches. `idempotencyKey` es obligatoria: la misma clave en un reintento devuelve la misma partida. */
export async function createMatch(
  request: CreateMatchRequest,
  idempotencyKey: string,
  fetchFn: FetchFn = fetch,
): Promise<ApiResult<CreatedMatch>> {
  const result = await call<CreatedMatch>(fetchFn, '/api/matches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(request),
  });
  if (result.ok && typeof result.value?.matchId !== 'string') {
    return { ok: false, error: { status: 502, code: 'SERVICES_UNAVAILABLE', message: '' } };
  }
  return result;
}

/** POST /api/matches/{matchId}/join. No depende de un GET previo: una partida privada da 404 al GET antes de unirse. */
export async function joinMatch(matchId: string, fetchFn: FetchFn = fetch): Promise<ApiResult<GameState>> {
  return call<GameState>(fetchFn, `/api/matches/${encodeURIComponent(matchId)}/join`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
}
