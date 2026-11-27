import { useEffect, useRef, useState } from 'react';
import { fetchAnalysisResult, fetchAnalysisStatus, requestAnalysis } from './api';
import type { AnalysisResultData, AnalysisStatus } from './types';

interface AnalysisModalProps {
  gameId: string;
  onClose: () => void;
}

type ModalState =
  | { kind: 'requesting' }
  | { kind: 'polling'; status: AnalysisStatus; elapsedSeconds: number }
  | { kind: 'completed'; status: AnalysisStatus; result: AnalysisResultData }
  | { kind: 'failed'; message: string; retryable: boolean; status?: AnalysisStatus };

const CLASSIFICATION_LABEL: Record<string, { label: string; badge: string }> = {
  best: { label: '¡Mejor jugada!', badge: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30' },
  good: { label: 'Buena', badge: 'bg-blue-500/10 text-blue-600 border-blue-500/30' },
  inaccuracy: { label: 'Imprecisión', badge: 'bg-amber-500/10 text-amber-700 border-amber-500/30' },
  mistake: { label: 'Error', badge: 'bg-orange-500/10 text-orange-700 border-orange-500/30' },
  blunder: { label: 'Grave error', badge: 'bg-red-500/10 text-red-600 border-red-500/30' },
  book: { label: 'Teoría', badge: 'bg-purple-500/10 text-purple-600 border-purple-500/30' },
};

export default function AnalysisModal({ gameId, onClose }: AnalysisModalProps) {
  const [state, setState] = useState<ModalState>({ kind: 'requesting' });
  const [attempt, setAttempt] = useState(0);
  const activeStatusRef = useRef<AnalysisStatus | null>(null);

  // Cierra con Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  // Solicitud inicial o reintento
  useEffect(() => {
    let cancelled = false;

    void requestAnalysis(gameId).then((res) => {
      if (cancelled) return;
      if (res.kind === 'unauthenticated') {
        setState({
          kind: 'failed',
          message: 'Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.',
          retryable: false,
        });
        return;
      }
      if (res.kind !== 'ok') {
        setState({
          kind: 'failed',
          message: res.message,
          retryable: false,
        });
        return;
      }

      activeStatusRef.current = res.status;

      if (res.status.status === 'completed') {
        void fetchAnalysisResult(res.status.analysisId).then((resResult) => {
          if (cancelled) return;
          if (resResult.kind === 'ok') {
            setState({ kind: 'completed', status: res.status, result: resResult.result });
          } else {
            setState({
              kind: 'failed',
              message: 'El análisis figura como terminado pero no se pudo descargar el informe.',
              retryable: true,
              status: res.status,
            });
          }
        });
      } else if (res.status.status === 'failed') {
        setState({
          kind: 'failed',
          message: res.status.error || 'El análisis falló en el motor de evaluación.',
          retryable: res.status.retryable,
          status: res.status,
        });
      } else {
        setState({ kind: 'polling', status: res.status, elapsedSeconds: 0 });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [gameId, attempt]);

  const pollingAnalysisId = state.kind === 'polling' ? state.status.analysisId : null;

  // Polling cada 3 segundos si está en pending o processing (contrato: cada 3 a 5 segundos)
  useEffect(() => {
    if (!pollingAnalysisId) return;

    let cancelled = false;

    const interval = setInterval(() => {
      setState((prev) => (prev.kind === 'polling' ? { ...prev, elapsedSeconds: prev.elapsedSeconds + 3 } : prev));

      void fetchAnalysisStatus(pollingAnalysisId).then((res) => {
        if (cancelled) return;
        if (res.kind === 'ok') {
          activeStatusRef.current = res.status;

          if (res.status.status === 'completed') {
            void fetchAnalysisResult(pollingAnalysisId).then((resResult) => {
              if (cancelled) return;
              if (resResult.kind === 'ok') {
                setState({ kind: 'completed', status: res.status, result: resResult.result });
              } else {
                setState({
                  kind: 'failed',
                  message: 'No se pudo obtener el resultado del análisis terminado.',
                  retryable: true,
                  status: res.status,
                });
              }
            });
          } else if (res.status.status === 'failed') {
            setState({
              kind: 'failed',
              message: res.status.error || 'El análisis falló en el procesamiento.',
              retryable: res.status.retryable,
              status: res.status,
            });
          }
        }
      });
    }, 3000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [pollingAnalysisId]);

  const handleRetry = () => {
    setState({ kind: 'requesting' });
    setAttempt((n) => n + 1);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="analysis-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/60 backdrop-blur-sm overflow-y-auto"
    >
      <div className="relative w-full max-w-4xl bg-surface rounded-2xl shadow-2xl border border-outline-variant/40 overflow-hidden flex flex-col max-h-[92vh] my-auto">
        {/* Cabecera */}
        <header className="px-5 py-4 border-b border-outline-variant/30 bg-surface-container-low flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <span className="material-symbols-outlined text-[24px]">psychology</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="analysis-dialog-title" className="font-headline-sm text-headline-sm text-on-surface">
                  Análisis con Tutor IA
                </h2>
                <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary font-label-sm text-label-sm uppercase tracking-wider">
                  Stockfish
                </span>
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant font-mono">
                Partida {gameId.slice(0, 8)}…
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar modal de análisis"
            className="w-9 h-9 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-on-surface flex items-center justify-center transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </header>

        {/* Contenido según el estado */}
        <div className="p-5 sm:p-6 overflow-y-auto flex-1 flex flex-col gap-5">
          {state.kind === 'requesting' && (
            <div className="py-12 flex flex-col items-center justify-center gap-4 text-center">
              <div className="w-12 h-12 rounded-full border-4 border-primary/20 border-t-primary animate-spin"></div>
              <div>
                <p className="font-headline-sm text-headline-sm text-on-surface">Conectando con el Tutor IA…</p>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">
                  Enviando partida al motor de análisis para su evaluación posicional.
                </p>
              </div>
            </div>
          )}

          {state.kind === 'polling' && (
            <div className="py-10 flex flex-col items-center justify-center gap-4 text-center">
              <div className="relative flex items-center justify-center">
                <div className="w-16 h-16 rounded-full bg-primary/10 text-primary flex items-center justify-center animate-pulse">
                  <span className="material-symbols-outlined text-[36px]">auto_awesome</span>
                </div>
              </div>
              <div className="max-w-md">
                <p className="font-headline-sm text-headline-sm text-on-surface">
                  {state.status.status === 'processing'
                    ? 'Evaluando jugadas en profundidad…'
                    : 'Análisis en cola de espera…'}
                </p>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">
                  Profundidad: {state.status.depth} capas · Tiempo transcurrido: {state.elapsedSeconds}s
                </p>
              </div>

              {/* Aviso si transcurren más de 2 minutos (120 segundos) según contrato 5.3 y 5.4.6 */}
              {state.elapsedSeconds >= 120 && (
                <div
                  role="status"
                  className="mt-4 p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-800 text-left max-w-lg flex items-start gap-3"
                >
                  <span className="material-symbols-outlined text-amber-600 shrink-0">hourglass_top</span>
                  <div>
                    <p className="font-label-lg text-label-lg font-semibold">El análisis sigue en proceso</p>
                    <p className="font-body-sm text-body-sm text-amber-800/90 mt-0.5">
                      Las posiciones complejas requieren más tiempo de cálculo en Stockfish. La ventana puede permanecer
                      abierta mientras finaliza la generación del informe.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {state.kind === 'failed' && (
            <div className="py-8 flex flex-col items-center justify-center gap-4 text-center">
              <div className="w-14 h-14 rounded-full bg-error-container text-error flex items-center justify-center">
                <span className="material-symbols-outlined text-[32px]">warning</span>
              </div>
              <div className="max-w-md">
                <h3 className="font-headline-sm text-headline-sm text-on-surface">No se pudo completar el análisis</h3>
                <p className="font-body-md text-body-md text-on-surface-variant mt-2">{state.message}</p>
              </div>
              {state.retryable ? (
                <button
                  type="button"
                  onClick={handleRetry}
                  className="mt-2 inline-flex items-center gap-2 px-space-lg py-space-xs rounded-lg bg-primary text-on-primary font-label-lg text-label-lg shadow-sm hover:bg-primary-container transition-colors cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[20px]">refresh</span>
                  Reintentar análisis
                </button>
              ) : (
                <p className="font-body-sm text-body-sm text-on-surface-variant italic">
                  Este resultado no es reintentable automáticamente.
                </p>
              )}
            </div>
          )}

          {state.kind === 'completed' && (
            <div className="flex flex-col gap-6">
              {/* Explicación pedagógica del Tutor */}
              <section className="p-4 sm:p-5 rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm flex flex-col gap-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                    <span className="material-symbols-outlined text-[20px]">record_voice_over</span>
                  </div>
                  <h3 className="font-headline-sm text-headline-sm text-on-surface">Explicación del Tutor IA</h3>
                </div>
                <div className="font-body-md text-body-md text-on-surface leading-relaxed whitespace-pre-line bg-surface p-4 rounded-xl border border-outline-variant/20">
                  {state.result.explanation || 'El análisis pedagógico de la partida concluyó satisfactoriamente.'}
                </div>
              </section>

              {/* Resumen de precisión White vs Black si está disponible */}
              {state.result.summary && (
                <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Blancas */}
                  <div className="p-4 rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm flex flex-col gap-3">
                    <div className="flex items-center justify-between pb-2 border-b border-outline-variant/30">
                      <span className="flex items-center gap-2 font-label-lg text-label-lg text-on-surface">
                        <span className="w-4 h-4 rounded-full border border-outline bg-[#fdf6ea]"></span>
                        Blancas
                      </span>
                      <span className="font-body-sm text-body-sm text-on-surface-variant font-mono">
                        Pérdida media: {state.result.summary.white.averageCpLoss.toFixed(1)} cp
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="p-2 rounded-xl bg-surface border border-outline-variant/20">
                        <span className="font-headline-sm text-headline-sm text-emerald-600 block">
                          {state.result.summary.white.best}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Mejores</span>
                      </div>
                      <div className="p-2 rounded-xl bg-surface border border-outline-variant/20">
                        <span className="font-headline-sm text-headline-sm text-blue-600 block">
                          {state.result.summary.white.good}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Buenas</span>
                      </div>
                      <div className="p-2 rounded-xl bg-surface border border-outline-variant/20">
                        <span className="font-headline-sm text-headline-sm text-amber-600 block">
                          {state.result.summary.white.inaccuracy}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Imprecisas</span>
                      </div>
                      <div className="p-2 rounded-xl bg-surface border border-outline-variant/20">
                        <span className="font-headline-sm text-headline-sm text-orange-600 block">
                          {state.result.summary.white.mistake}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Errores</span>
                      </div>
                      <div className="p-2 rounded-xl bg-surface border border-outline-variant/20 col-span-2">
                        <span className="font-headline-sm text-headline-sm text-red-600 block">
                          {state.result.summary.white.blunder}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Graves errores</span>
                      </div>
                    </div>
                  </div>

                  {/* Negras */}
                  <div className="p-4 rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm flex flex-col gap-3">
                    <div className="flex items-center justify-between pb-2 border-b border-outline-variant/30">
                      <span className="flex items-center gap-2 font-label-lg text-label-lg text-on-surface">
                        <span className="w-4 h-4 rounded-full border border-outline bg-[#2a170c]"></span>
                        Negras
                      </span>
                      <span className="font-body-sm text-body-sm text-on-surface-variant font-mono">
                        Pérdida media: {state.result.summary.black.averageCpLoss.toFixed(1)} cp
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="p-2 rounded-xl bg-surface border border-outline-variant/20">
                        <span className="font-headline-sm text-headline-sm text-emerald-600 block">
                          {state.result.summary.black.best}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Mejores</span>
                      </div>
                      <div className="p-2 rounded-xl bg-surface border border-outline-variant/20">
                        <span className="font-headline-sm text-headline-sm text-blue-600 block">
                          {state.result.summary.black.good}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Buenas</span>
                      </div>
                      <div className="p-2 rounded-xl bg-surface border border-outline-variant/20">
                        <span className="font-headline-sm text-headline-sm text-amber-600 block">
                          {state.result.summary.black.inaccuracy}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Imprecisas</span>
                      </div>
                      <div className="p-2 rounded-xl bg-surface border border-outline-variant/20">
                        <span className="font-headline-sm text-headline-sm text-orange-600 block">
                          {state.result.summary.black.mistake}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Errores</span>
                      </div>
                      <div className="p-2 rounded-xl bg-surface border border-outline-variant/20 col-span-2">
                        <span className="font-headline-sm text-headline-sm text-red-600 block">
                          {state.result.summary.black.blunder}
                        </span>
                        <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Graves errores</span>
                      </div>
                    </div>
                  </div>
                </section>
              )}

              {/* Detalle jugada por jugada */}
              {Array.isArray(state.result.moves) && state.result.moves.length > 0 && (
                <section className="p-4 sm:p-5 rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm flex flex-col gap-3">
                  <h3 className="font-headline-sm text-headline-sm text-on-surface">Evaluación jugada por jugada</h3>
                  <div className="overflow-x-auto max-h-80 border border-outline-variant/20 rounded-xl bg-surface">
                    <table className="w-full text-left font-body-sm text-body-sm">
                      <thead className="bg-surface-container-high sticky top-0 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">
                        <tr>
                          <th className="py-2.5 px-3">#</th>
                          <th className="py-2.5 px-3">Jugada</th>
                          <th className="py-2.5 px-3">Calidad</th>
                          <th className="py-2.5 px-3">Mejor opción</th>
                          <th className="py-2.5 px-3 text-right">Pérdida (cp)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-outline-variant/20 font-mono text-[13px]">
                        {state.result.moves.map((m, idx) => {
                          const cls = m.classification ? CLASSIFICATION_LABEL[m.classification] : null;
                          return (
                            <tr key={idx} className="hover:bg-surface-container-low transition-colors">
                              <td className="py-2 px-3 text-on-surface-variant">
                                {Math.floor((m.ply - 1) / 2) + 1}.{m.color === 'white' ? '' : '..'}
                              </td>
                              <td className="py-2 px-3 font-semibold text-on-surface">
                                <span
                                  className={`inline-block w-2.5 h-2.5 rounded-full mr-1.5 border border-outline ${
                                    m.color === 'white' ? 'bg-[#fdf6ea]' : 'bg-[#2a170c]'
                                  }`}
                                ></span>
                                {m.san || m.uci}
                              </td>
                              <td className="py-2 px-3 font-sans">
                                {cls ? (
                                  <span
                                    className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold border ${cls.badge}`}
                                  >
                                    {cls.label}
                                  </span>
                                ) : (
                                  <span className="text-on-surface-variant text-[11px]">—</span>
                                )}
                              </td>
                              <td className="py-2 px-3 text-on-surface-variant font-sans">
                                {m.bestMove?.san ? (
                                  <span className="text-primary font-semibold font-mono">{m.bestMove.san}</span>
                                ) : (
                                  '—'
                                )}
                              </td>
                              <td className="py-2 px-3 text-right text-on-surface-variant">
                                {m.cpLoss !== null && m.cpLoss !== undefined ? `-${m.cpLoss}` : '—'}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </div>
          )}
        </div>

        {/* Pie */}
        <footer className="px-5 py-3 border-t border-outline-variant/30 bg-surface-container-low flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-space-md py-space-xs rounded-lg bg-surface-container-high text-on-surface font-label-lg text-label-lg hover:bg-surface-container-highest transition-colors cursor-pointer"
          >
            Cerrar
          </button>
        </footer>
      </div>
    </div>
  );
}
