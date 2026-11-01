import type { PlayerStats, StatsPageData } from './types';

const percent = (part: number, total: number) => (total === 0 ? 0 : Math.round((part / total) * 100));

interface CardProps {
  label: string;
  value: number;
  tone: string;
}

function StatCard({ label, value, tone }: CardProps) {
  return (
    <div className="p-space-md rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm flex flex-col gap-1">
      <span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant">{label}</span>
      <span className={`font-headline-lg text-headline-lg ${tone}`}>{value}</span>
    </div>
  );
}

function Breakdown({ stats }: { stats: PlayerStats }) {
  const parts = [
    { label: 'Victorias', value: stats.wins, bar: 'bg-secondary' },
    { label: 'Tablas', value: stats.draws, bar: 'bg-tertiary' },
    { label: 'Derrotas', value: stats.losses, bar: 'bg-primary' },
  ];
  return (
    <div className="p-space-md rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm flex flex-col gap-space-sm">
      <h2 className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant">Reparto</h2>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-surface-container-highest" aria-hidden="true">
        {parts.map((p) => (
          <div key={p.label} className={p.bar} style={{ width: `${percent(p.value, stats.gamesPlayed)}%` }}></div>
        ))}
      </div>
      <ul className="grid grid-cols-3 gap-space-xs font-body-sm text-body-sm text-on-surface-variant">
        {parts.map((p) => (
          <li key={p.label} className="flex items-center gap-space-xs">
            <span className={`w-3 h-3 rounded-full ${p.bar}`}></span>
            {p.label}: <strong className="text-on-surface">{percent(p.value, stats.gamesPlayed)} %</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Contenido de /estadisticas. Componente puro (sin estado ni efectos), apto para renderizarse en
 * el servidor con los datos que trae loadStatsPage. El caso sin sesión no llega aquí: el servidor
 * redirige al login antes de renderizar.
 */
export default function StatsView({ data }: { data: Exclude<StatsPageData, { kind: 'unauthenticated' }> }) {
  return (
    <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased px-gutter-mobile md:px-margin py-space-xl">
      <div className="max-w-3xl mx-auto flex flex-col gap-space-lg">
        <header className="flex flex-col gap-space-xs">
          <span className="font-label-sm text-label-sm uppercase tracking-widest text-primary">Tu progreso</span>
          <h1 className="font-headline-lg text-headline-lg text-on-surface">Estadísticas</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Partidas multijugador terminadas con resultado. Las partidas locales y contra Botcito no cuentan.
          </p>
        </header>

        {data.kind === 'unavailable' && (
          <div
            role="alert"
            className="p-space-md rounded-xl bg-error-container text-on-error-container font-body-md text-body-md flex items-center gap-space-xs"
          >
            <span className="material-symbols-outlined text-[20px]">cloud_off</span>
            No disponible en este momento. Vuelve a cargar la página en unos segundos.
          </div>
        )}

        {data.kind === 'ok' && data.stats.gamesPlayed === 0 && (
          <div className="p-space-lg rounded-2xl bg-surface-container-low border border-outline-variant/30 text-center flex flex-col items-center gap-space-xs">
            <span className="material-symbols-outlined text-[40px] text-on-surface-variant">sports_esports</span>
            <p className="font-headline-sm text-headline-sm text-on-surface">Aún no has jugado partidas online</p>
          </div>
        )}

        {data.kind === 'ok' && data.stats.gamesPlayed > 0 && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-space-sm">
              <StatCard label="Jugadas" value={data.stats.gamesPlayed} tone="text-on-surface" />
              <StatCard label="Victorias" value={data.stats.wins} tone="text-secondary" />
              <StatCard label="Derrotas" value={data.stats.losses} tone="text-primary" />
              <StatCard label="Tablas" value={data.stats.draws} tone="text-tertiary" />
            </div>
            <Breakdown stats={data.stats} />
          </>
        )}
      </div>
    </div>
  );
}
