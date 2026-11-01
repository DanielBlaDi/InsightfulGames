/** GET /stats/me (contrato v9, sección 8): solo partidas multiplayer con resultado. */
export interface PlayerStats {
  gamesPlayed: number;
  wins: number;
  losses: number;
  draws: number;
}

/** Lo que la página de estadísticas recibe del servidor antes de renderizar. */
export type StatsPageData =
  | { kind: 'ok'; stats: PlayerStats }
  /** Sin sesión válida: el servidor responde 302 a /login?next=/estadisticas (sección 6). */
  | { kind: 'unauthenticated'; redirectTo: string }
  /** Profile/Stats o el gateway no respondieron: se muestra la página con aviso. */
  | { kind: 'unavailable' };

export const STATS_PATH = '/estadisticas';
