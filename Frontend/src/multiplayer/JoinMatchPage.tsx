import { useEffect, useState } from 'react';
import { navigate } from 'vike/client/router';
import { loginUrl, probeSession } from '../auth/session';
import AccountNav from '../components/AccountNav';
import { describeError, joinMatch } from './api';
import type { MatchApiError } from './api';
import { invitePath, isMatchId, matchPath } from './types';

type JoinState =
  | { kind: 'checking' }
  | { kind: 'ready' }
  | { kind: 'joining' }
  | { kind: 'error'; error: MatchApiError };

const BUTTON =
  'px-space-lg py-space-sm rounded-xl bg-primary text-on-primary font-label-lg text-label-lg shadow-md hover:bg-primary-container transition-all inline-flex items-center gap-space-xs cursor-pointer disabled:opacity-70 disabled:cursor-wait';
const SECONDARY =
  'px-space-md py-space-sm rounded-xl bg-surface-container-high text-on-surface font-label-lg text-label-lg hover:bg-surface-container-highest transition-colors inline-flex items-center gap-space-xs';

/**
 * /unirse/{matchId}: invitación. Sin sesión va al login y vuelve aquí con `next`. Unirse es
 * POST /api/matches/{id}/join directamente: no hay GET previo (una partida privada responde 404
 * al GET hasta que el invitado se une).
 */
export default function JoinMatchPage({ matchId }: { matchId: string }) {
  const valid = isMatchId(matchId);
  const [state, setState] = useState<JoinState>(
    valid ? { kind: 'checking' } : { kind: 'error', error: { status: 404, code: 'MATCH_NOT_FOUND', message: '' } },
  );

  useEffect(() => {
    if (!valid) return;
    let active = true;
    void probeSession().then((status) => {
      if (!active) return;
      if (status === 'anonymous') window.location.replace(loginUrl(invitePath(matchId)));
      else setState({ kind: 'ready' });
    });
    return () => {
      active = false;
    };
  }, [matchId, valid]);

  const join = async () => {
    setState({ kind: 'joining' });
    const result = await joinMatch(matchId);
    if (result.ok) {
      await navigate(matchPath(matchId));
      return;
    }
    if (result.error.code === 'UNAUTHORIZED') {
      window.location.assign(loginUrl(invitePath(matchId)));
      return;
    }
    setState({ kind: 'error', error: result.error });
  };

  const error = state.kind === 'error' ? state.error : null;
  // Quien ya juega en la partida (el creador, o el invitado que recarga) puede ir directo al tablero.
  const canOpenMatch = error && (error.code === 'ALREADY_PARTICIPANT' || error.code === 'MATCH_NOT_WAITING');
  const canRetry = error && (error.code === 'SERVICES_UNAVAILABLE' || error.code === 'NETWORK' || error.status >= 500);

  return (
    <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased">
      <AccountNav />
      <main className="px-gutter-mobile md:px-margin py-space-xl">
        <section className="max-w-xl mx-auto p-space-lg rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm flex flex-col gap-space-md text-center items-center">
          <span className="w-14 h-14 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
            <span className="material-symbols-outlined text-[32px]" aria-hidden="true">
              swords
            </span>
          </span>
          <h1 className="font-headline-md text-headline-md text-on-surface">Invitación a una partida de ajedrez</h1>

          {state.kind === 'checking' && (
            <p role="status" className="text-on-surface-variant">
              Comprobando tu sesión…
            </p>
          )}

          {(state.kind === 'ready' || state.kind === 'joining') && (
            <>
              <p className="text-on-surface-variant">Otra persona te invitó a jugar online. El color lo eligió quien creó la partida.</p>
              <button type="button" className={BUTTON} disabled={state.kind === 'joining'} onClick={() => void join()}>
                <span className={`material-symbols-outlined text-[18px] ${state.kind === 'joining' ? 'animate-spin' : ''}`}>
                  {state.kind === 'joining' ? 'progress_activity' : 'login'}
                </span>
                {state.kind === 'joining' ? 'Uniéndote…' : 'Unirme a la partida'}
              </button>
            </>
          )}

          {error && (
            <>
              <p role="alert" className="p-space-sm rounded-xl bg-error-container text-on-error-container font-body-md text-body-md w-full">
                {describeError(error)}
              </p>
              <div className="flex flex-wrap gap-space-sm justify-center">
                {canOpenMatch && (
                  <a href={matchPath(matchId)} className={BUTTON}>
                    <span className="material-symbols-outlined text-[18px]">play_arrow</span>
                    Ir a la partida
                  </a>
                )}
                {canRetry && (
                  <button type="button" className={BUTTON} onClick={() => void join()}>
                    <span className="material-symbols-outlined text-[18px]">refresh</span>
                    Reintentar
                  </button>
                )}
                <a href="/multijugador" className={SECONDARY}>
                  Crear otra partida
                </a>
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  );
}
