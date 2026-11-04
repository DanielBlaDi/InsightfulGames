import { useEffect, useState } from 'react';
import { loginUrl } from '../auth/session';
import AccountNav from '../components/AccountNav';
import type { Color, EndReason, GameMode, GameResult, GameStatus } from '../game/types';
import AnalysisModal from '../tutor/AnalysisModal';
import { fetchGameHistory } from './api';
import type { GameSummary, HistoryFilter } from './types';

export const HISTORIAL_PATH = '/historial';

type HistoryState =
  | { kind: 'loading' }
  | { kind: 'ok'; items: GameSummary[]; nextCursor: string | null }
  | { kind: 'empty' }
  | { kind: 'unavailable' }
  | { kind: 'redirecting' };

const MODE_LABEL: Record<GameMode, { label: string; icon: string }> = {
  local: { label: 'Partida local', icon: 'group' },
  vs_bot: { label: 'Contra Botcito', icon: 'smart_toy' },
  multiplayer: { label: 'Multijugador online', icon: 'public' },
};

const REASON_LABEL: Record<EndReason, string> = {
  checkmate: 'por jaque mate',
  stalemate: 'por ahogado',
  surrender: 'por rendición',
  draw: 'por acuerdo',
  timeout: 'por tiempo',
  abandonment: 'por abandono',
  expired: 'caducada',
  account_deleted: 'por cuenta eliminada',
};

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('es', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function resultBadge(
  status: GameStatus,
  result: GameResult | null,
  endReason?: EndReason | null,
  myColor?: Color | null
) {
  if (status === 'waiting') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-700 text-[12px] font-semibold border border-amber-500/20">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>
        Esperando rival
      </span>
    );
  }
  if (status === 'in_progress') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-700 text-[12px] font-semibold border border-blue-500/20">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
        En curso
      </span>
    );
  }
  if (result === 'draw') {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant text-[12px] font-semibold border border-outline-variant/30">
        Tablas {endReason ? `(${REASON_LABEL[endReason] ?? ''})` : ''}
      </span>
    );
  }
  if (result === 'white' || result === 'black') {
    const won = myColor ? result === myColor : null;
    const label =
      won === true
        ? '¡Victoria!'
        : won === false
        ? 'Derrota'
        : `Ganó ${result === 'white' ? 'Blancas' : 'Negras'}`;
    const tone =
      won === true
        ? 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20'
        : won === false
        ? 'bg-rose-500/10 text-rose-700 border-rose-500/20'
        : 'bg-primary/10 text-primary border-primary/20';
    return (
      <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[12px] font-semibold border ${tone}`}>
        {label} {endReason && endReason !== 'expired' ? `· ${REASON_LABEL[endReason] ?? ''}` : ''}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant text-[12px] font-semibold">
      Finalizada
    </span>
  );
}

export default function HistoryPage() {
  const [state, setState] = useState<HistoryState>({ kind: 'loading' });
  const [filter, setFilter] = useState<HistoryFilter>('all');
  const [loadingMore, setLoadingMore] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [analyzingGameId, setAnalyzingGameId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchGameHistory(null, 20).then((res) => {
      if (!active) return;
      if (res.kind === 'unauthenticated') {
        setState({ kind: 'redirecting' });
        window.location.replace(loginUrl(HISTORIAL_PATH));
      } else if (res.kind === 'ok') {
        if (res.page.items.length === 0) {
          setState({ kind: 'empty' });
        } else {
          setState({ kind: 'ok', items: res.page.items, nextCursor: res.page.nextCursor });
        }
      } else {
        setState({ kind: 'unavailable' });
      }
    });

    return () => {
      active = false;
    };
  }, [attempt]);

  const loadMore = async () => {
    if (state.kind !== 'ok' || !state.nextCursor || loadingMore) return;
    setLoadingMore(true);

    const res = await fetchGameHistory(state.nextCursor, 20);
    setLoadingMore(false);

    if (res.kind === 'ok') {
      setState((prev) =>
        prev.kind === 'ok'
          ? {
              kind: 'ok',
              items: [...prev.items, ...res.page.items],
              nextCursor: res.page.nextCursor,
            }
          : prev
      );
    }
  };

  const handleRetry = () => {
    setState({ kind: 'loading' });
    setAttempt((n) => n + 1);
  };

  const filterItems = (items: GameSummary[]) => {
    switch (filter) {
      case 'finished':
        return items.filter((g) => g.status === 'finished');
      case 'in_progress':
        return items.filter((g) => g.status === 'in_progress');
      case 'waiting':
        return items.filter((g) => g.status === 'waiting');
      default:
        return items;
    }
  };

  const visibleItems = state.kind === 'ok' ? filterItems(state.items) : [];

  return (
    <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased">
      <AccountNav current="historial" />

      <main className="px-gutter-mobile md:px-margin py-space-xl">
        <div className="max-w-4xl mx-auto flex flex-col gap-space-lg">
          {/* Encabezado */}
          <header className="flex flex-col md:flex-row md:items-end justify-between gap-space-md">
            <div className="flex flex-col gap-space-xs">
              <span className="font-label-sm text-label-sm uppercase tracking-widest text-primary">Tus partidas</span>
              <h1 className="font-headline-lg text-headline-lg text-on-surface">Historial de partidas</h1>
              <p className="font-body-md text-body-md text-on-surface-variant">
                Consulta tus partidas jugadas, invitaciones y obtén el análisis pedagógico del Tutor IA.
              </p>
            </div>
            <div className="flex items-center gap-space-xs shrink-0">
              <a
                href="/multijugador"
                className="inline-flex items-center gap-space-xs px-space-md py-space-xs rounded-lg bg-surface-container-high text-on-surface font-label-lg text-label-lg hover:bg-surface-container-highest transition-colors shadow-sm"
              >
                <span className="material-symbols-outlined text-[18px]">add</span>
                Nueva online
              </a>
              <a
                href="/"
                className="inline-flex items-center gap-space-xs px-space-md py-space-xs rounded-lg bg-primary text-on-primary font-label-lg text-label-lg hover:bg-primary-container transition-colors shadow-sm"
              >
                <span className="material-symbols-outlined text-[18px]">sports_esports</span>
                Jugar
              </a>
            </div>
          </header>

          {/* Filtros por pestaña: separa invitaciones y partidas no jugadas según el contrato */}
          {state.kind === 'ok' && (
            <div className="flex flex-wrap items-center gap-space-xs border-b border-outline-variant/30 pb-space-xs">
              {(
                [
                  { id: 'all', label: 'Todas', count: state.items.length },
                  { id: 'finished', label: 'Terminadas', count: state.items.filter((g) => g.status === 'finished').length },
                  { id: 'in_progress', label: 'En curso', count: state.items.filter((g) => g.status === 'in_progress').length },
                  { id: 'waiting', label: 'Invitaciones pendientes', count: state.items.filter((g) => g.status === 'waiting').length },
                ] as const
              ).map((tab) => {
                const active = filter === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setFilter(tab.id)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-label-md text-label-md transition-colors cursor-pointer ${
                      active
                        ? 'bg-primary text-on-primary shadow-sm'
                        : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high'
                    }`}
                  >
                    <span>{tab.label}</span>
                    <span
                      className={`text-[11px] px-1.5 py-0.2 rounded-full ${
                        active ? 'bg-on-primary/20 text-on-primary' : 'bg-surface-container-highest text-on-surface-variant'
                      }`}
                    >
                      {tab.count}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Estado de carga o redirección */}
          {(state.kind === 'loading' || state.kind === 'redirecting') && (
            <div className="py-12 flex flex-col items-center justify-center gap-3 text-center">
              <div className="w-10 h-10 rounded-full border-4 border-primary/20 border-t-primary animate-spin"></div>
              <p className="font-body-md text-body-md text-on-surface-variant">
                {state.kind === 'loading' ? 'Cargando tu historial de partidas…' : 'Tu sesión venció. Redirigiendo…'}
              </p>
            </div>
          )}

          {/* Estado no disponible */}
          {state.kind === 'unavailable' && (
            <div
              role="alert"
              className="p-space-lg rounded-2xl bg-surface-container-low border border-outline-variant/30 text-center flex flex-col items-center gap-space-sm"
            >
              <span className="material-symbols-outlined text-[40px] text-on-surface-variant">cloud_off</span>
              <h2 className="font-headline-sm text-headline-sm text-on-surface">No se pudo cargar el historial</h2>
              <p className="font-body-md text-body-md text-on-surface-variant max-w-md">
                El servicio de partidas no respondió en este momento. Tu sesión sigue activa.
              </p>
              <button
                type="button"
                onClick={handleRetry}
                className="mt-2 px-space-md py-space-xs rounded-lg bg-primary text-on-primary font-label-lg text-label-lg shadow-sm hover:bg-primary-container transition-colors cursor-pointer"
              >
                Reintentar
              </button>
            </div>
          )}

          {/* Estado vacío */}
          {state.kind === 'empty' && (
            <div className="p-space-xl rounded-2xl bg-surface-container-low border border-outline-variant/30 text-center flex flex-col items-center gap-space-sm">
              <div className="w-16 h-16 rounded-full bg-primary/10 text-primary flex items-center justify-center">
                <span className="material-symbols-outlined text-[36px]">sports_esports</span>
              </div>
              <h2 className="font-headline-sm text-headline-sm text-on-surface">Aún no has jugado partidas</h2>
              <p className="font-body-md text-body-md text-on-surface-variant max-w-md">
                Cuando juegues partidas locales, contra Botcito o en línea, aparecerán aquí con sus resultados y análisis del Tutor IA.
              </p>
              <div className="flex gap-space-xs mt-2">
                <a
                  href="/"
                  className="px-space-md py-space-xs rounded-lg bg-primary text-on-primary font-label-lg text-label-lg shadow-sm hover:bg-primary-container transition-colors"
                >
                  Jugar ahora
                </a>
              </div>
            </div>
          )}

          {/* Lista de partidas */}
          {state.kind === 'ok' && (
            <>
              {visibleItems.length === 0 ? (
                <div className="p-space-lg rounded-2xl bg-surface-container-low border border-outline-variant/30 text-center flex flex-col items-center gap-2">
                  <p className="font-body-md text-body-md text-on-surface-variant">
                    No hay partidas en esta categoría.
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {visibleItems.map((game) => {
                    const modeInfo = MODE_LABEL[game.mode] ?? { label: game.mode, icon: 'extension' };
                    const isFinished = game.status === 'finished';

                    return (
                      <article
                        key={game.gameId}
                        className="p-4 sm:p-5 rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm hover:shadow-md transition-shadow flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                      >
                        <div className="flex items-start gap-3.5">
                          <div className="w-11 h-11 rounded-xl bg-surface-container-high flex items-center justify-center text-primary shrink-0 mt-0.5">
                            <span className="material-symbols-outlined text-[24px]">{modeInfo.icon}</span>
                          </div>
                          <div className="flex flex-col gap-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-label-lg text-label-lg text-on-surface font-semibold">
                                {modeInfo.label}
                              </span>
                              {resultBadge(game.status, game.result, game.endReason, game.color)}
                            </div>
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-body-sm text-body-sm text-on-surface-variant">
                              <span className="flex items-center gap-1">
                                <span className="material-symbols-outlined text-[16px]">schedule</span>
                                {formatDate(game.createdAt)}
                              </span>
                              {game.color && (
                                <span className="flex items-center gap-1">
                                  <span
                                    className={`w-3 h-3 rounded-full border border-outline ${
                                      game.color === 'white' ? 'bg-[#fdf6ea]' : 'bg-[#2a170c]'
                                    }`}
                                  ></span>
                                  Jugaste con {game.color === 'white' ? 'blancas' : 'negras'}
                                </span>
                              )}
                              <span className="font-mono text-[11px] text-on-surface-variant/70">
                                ID: {game.gameId.slice(0, 8)}…
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Botones de acción */}
                        <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                          {isFinished && (
                            <button
                              type="button"
                              onClick={() => setAnalyzingGameId(game.gameId)}
                              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-primary text-on-primary font-label-md text-label-md shadow-sm hover:bg-primary-container transition-colors cursor-pointer"
                              title="Solicitar análisis posicional y pedagógico con el Tutor IA"
                            >
                              <span className="material-symbols-outlined text-[18px]">psychology</span>
                              <span>Analizar partida</span>
                            </button>
                          )}

                          {game.status === 'waiting' && game.matchId && (
                            <a
                              href={`/partida/${game.matchId}`}
                              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-amber-600 text-white font-label-md text-label-md shadow-sm hover:bg-amber-700 transition-colors"
                            >
                              <span className="material-symbols-outlined text-[18px]">hourglass_top</span>
                              <span>Ir a sala de espera</span>
                            </a>
                          )}

                          {game.status === 'in_progress' && game.matchId && (
                            <a
                              href={`/partida/${game.matchId}`}
                              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-secondary text-on-secondary font-label-md text-label-md shadow-sm hover:opacity-95 transition-opacity"
                            >
                              <span className="material-symbols-outlined text-[18px]">play_arrow</span>
                              <span>Continuar partida</span>
                            </a>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}

              {/* Botón Cargar más */}
              {state.nextCursor && (
                <div className="flex justify-center pt-2">
                  <button
                    type="button"
                    disabled={loadingMore}
                    onClick={() => void loadMore()}
                    className="inline-flex items-center gap-2 px-space-lg py-space-xs rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-label-lg text-label-lg transition-colors cursor-pointer disabled:opacity-60"
                  >
                    <span className="material-symbols-outlined text-[18px]">
                      {loadingMore ? 'sync' : 'expand_more'}
                    </span>
                    {loadingMore ? 'Cargando más partidas…' : 'Cargar más partidas'}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </main>

      {/* Modal de análisis con Tutor IA */}
      {analyzingGameId && (
        <AnalysisModal gameId={analyzingGameId} onClose={() => setAnalyzingGameId(null)} />
      )}
    </div>
  );
}

