import { STATS_PATH } from './types';
import type { PlayerStats, StatsPageData } from './types';

interface LoadOptions {
  /** API_GATEWAY_URL del servidor del frontend, por ejemplo http://api-gateway-component:8080. */
  gatewayUrl: string;
  /** Cabecera Cookie tal como llegó del navegador. */
  cookie: string | undefined;
  fetchFn?: typeof fetch;
  timeoutMs?: number;
}

const isCount = (value: unknown): value is number => Number.isInteger(value) && (value as number) >= 0;

function isPlayerStats(value: unknown): value is PlayerStats {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return isCount(v.gamesPlayed) && isCount(v.wins) && isCount(v.losses) && isCount(v.draws);
}

/**
 * Datos de /estadisticas, pensado para ejecutarse en el servidor del frontend (sección 6): pide
 * la ruta pública GET /stats/me al gateway web con la misma cookie que envió el navegador. No usa
 * window ni rutas internas. Cuando el frontend tenga Vike, su +data.ts solo tiene que llamarlo.
 */
export async function loadStatsPage({
  gatewayUrl,
  cookie,
  fetchFn = fetch,
  timeoutMs = 5000,
}: LoadOptions): Promise<StatsPageData> {
  const redirectTo = `/login?next=${encodeURIComponent(STATS_PATH)}`;
  if (!cookie || !/(?:^|;\s*)session=/.test(cookie)) {
    return { kind: 'unauthenticated', redirectTo };
  }

  try {
    const response = await fetchFn(`${gatewayUrl.replace(/\/+$/, '')}/stats/me`, {
      headers: { Cookie: cookie, Accept: 'application/json' },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (response.status === 401) {
      return { kind: 'unauthenticated', redirectTo };
    }
    if (!response.ok) {
      return { kind: 'unavailable' };
    }
    const body: unknown = await response.json();
    return isPlayerStats(body) ? { kind: 'ok', stats: body } : { kind: 'unavailable' };
  } catch {
    return { kind: 'unavailable' };
  }
}
