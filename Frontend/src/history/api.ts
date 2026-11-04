import { apiUrl } from '../game/config';
import type { GamesPage, GameSummary } from './types';

export type HistoryResult =
  | { kind: 'ok'; page: GamesPage }
  | { kind: 'unauthenticated' }
  | { kind: 'unavailable' };

function isGameSummary(val: unknown): val is GameSummary {
  if (typeof val !== 'object' || val === null) return false;
  const v = val as Record<string, unknown>;
  return typeof v.gameId === 'string' && typeof v.mode === 'string' && typeof v.status === 'string';
}

function isGamesPage(val: unknown): val is GamesPage {
  if (typeof val !== 'object' || val === null) return false;
  const v = val as Record<string, unknown>;
  return Array.isArray(v.items) && v.items.every(isGameSummary);
}

/**
 * Pide GET /api/games con la cookie de sesión (sección 4.2 y 5.4.2).
 * Paginación de 20 elementos por página con cursor en base64url.
 */
export async function fetchGameHistory(
  cursor?: string | null,
  limit = 20,
  fetchFn: typeof fetch = fetch
): Promise<HistoryResult> {
  try {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set('cursor', cursor);

    const res = await fetchFn(apiUrl(`/games?${params.toString()}`), {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });

    if (res.status === 401) return { kind: 'unauthenticated' };
    if (!res.ok) return { kind: 'unavailable' };

    const body: unknown = await res.json().catch(() => null);
    if (!isGamesPage(body)) return { kind: 'unavailable' };

    return { kind: 'ok', page: body };
  } catch {
    return { kind: 'unavailable' };
  }
}

