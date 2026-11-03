import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { loginUrl } from '../auth/session';
import AccountNav from '../components/AccountNav';
import ChessBoard from '../game/ChessBoard';
import type { Color, EndReason, GameState } from '../game/types';
import {
  CLOSE_FORBIDDEN_ORIGIN,
  CLOSE_NORMAL,
  CLOSE_NOT_FOUND,
  CLOSE_UNAUTHORIZED,
  canMove,
  formatClock,
  remainingMs,
} from './matchSession';
import type { MatchView } from './matchSession';
import { useIdentity } from './useIdentity';
import { useMatchSocket } from './useMatchSocket';
import { colorOf, invitePath, isMatchId, matchPath, opposite } from './types';

const COLOR_LABEL: Record<Color, string> = { white: 'Blancas', black: 'Negras' };

const REASON: Record<EndReason, string> = {
  checkmate: 'por jaque mate',
  stalemate: 'por ahogado',
  surrender: 'por rendición',
  draw: 'por acuerdo',
  timeout: 'por tiempo',
  abandonment: 'por abandono (el rival no volvió a conectarse)',
  expired: '',
};

const CARD = 'p-space-md rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm flex flex-col gap-space-sm';
const BTN =
  'py-space-xs px-space-md rounded-lg font-label-lg text-label-lg transition-colors flex items-center justify-center gap-1 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed';
const BTN_NEUTRAL = `${BTN} bg-surface-container-high text-on-surface hover:bg-surface-container-highest`;
const BTN_PRIMARY = `${BTN} bg-primary text-on-primary hover:bg-primary-container`;
const ALERT = 'p-space-sm rounded-xl bg-error-container text-on-error-container font-body-sm text-body-sm';

function describeResult(state: GameState, gameOver: MatchView['gameOver'], me: Color | null): string {
  const result = gameOver?.result ?? state.result;
  const reason = gameOver?.endReason ?? state.endReason;
  if (reason === 'expired') return 'La partida caducó: nadie se unió a tiempo';
  if (result === null || result === undefined) return 'Partida finalizada';
  const why = reason ? REASON[reason] ?? '' : '';
  if (result === 'draw') return `Tablas ${why}`.trim();
  if (me) return `${result === me ? '¡Ganaste!' : 'Perdiste'} ${why}`.trim();
  return `Ganan las ${COLOR_LABEL[result].toLowerCase()} ${why}`.trim();
}

function describeClose(code: number | null, reason: string | null): string {
  if (code === CLOSE_UNAUTHORIZED) return 'Tu sesión venció. Inicia sesión de nuevo.';
  if (code === CLOSE_NOT_FOUND) return 'La partida no existe o no participas en ella. Si te invitaron, usa el enlace de invitación.';
  if (code === CLOSE_FORBIDDEN_ORIGIN) return 'El servidor rechazó la conexión desde este sitio (WS_ALLOWED_ORIGINS).';
  if (code === CLOSE_NORMAL && reason === 'reconnected') return 'Abriste esta partida en otra pestaña o dispositivo. Aquí se cerró la conexión.';
  return 'Se perdió la conexión con la partida.';
}

/** Hora actual que se actualiza cada medio segundo mientras `active`. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

function PlayerRow({ color, label, ms, active }: { color: Color; label: string; ms: number | null; active: boolean }) {
  const low = ms !== null && ms < 30_000;
  return (
    <div
      className={`flex items-center justify-between gap-space-sm p-space-sm rounded-xl border ${
        active ? 'border-primary bg-primary/10' : 'border-outline-variant/30 bg-surface'
      }`}
      data-testid={`clock-${color}`}
    >
      <span className="flex items-center gap-space-xs font-label-lg text-label-lg">
        <span className={`w-4 h-4 rounded-full border border-outline ${color === 'white' ? 'bg-[#fdf6ea]' : 'bg-[#2a170c]'}`}></span>
        {COLOR_LABEL[color]} · {label}
      </span>
      <span
        className={`font-mono text-[22px] tabular-nums ${low && active ? 'text-error' : 'text-on-surface'}`}
        aria-label={`Reloj de ${COLOR_LABEL[color].toLowerCase()}`}
      >
        {formatClock(ms)}
      </span>
    </div>
  );
}

function InviteBox({ matchId }: { matchId: string }) {
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const link = typeof window === 'undefined' ? invitePath(matchId) : `${window.location.origin}${invitePath(matchId)}`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      inputRef.current?.select(); // sin permiso de portapapeles: queda seleccionado para Ctrl+C
    }
  };
  return (
    <div className={CARD}>
      <p className="font-headline-sm text-headline-sm text-on-surface flex items-center gap-space-xs" role="status">
        <span className="material-symbols-outlined text-[22px] animate-pulse text-primary" aria-hidden="true">
          hourglass_top
        </span>
        Esperando a otro jugador
      </p>
      <p className="font-body-sm text-body-sm text-on-surface-variant">
        Comparte este enlace. Cuando la otra persona se una, la partida empezará sola.
      </p>
      <div className="flex gap-space-xs">
        <input
          ref={inputRef}
          readOnly
          value={link}
          aria-label="Enlace de invitación"
          onFocus={(e) => e.target.select()}
          className="flex-1 min-w-0 px-space-sm py-space-xs rounded-lg bg-surface border border-outline-variant font-mono text-[13px]"
        />
        <button type="button" onClick={() => void copy()} className={BTN_PRIMARY}>
          <span className="material-symbols-outlined text-[18px]">{copied ? 'check' : 'content_copy'}</span>
          {copied ? 'Copiado' : 'Copiar enlace'}
        </button>
      </div>
    </div>
  );
}

/** /partida/{matchId}: sala de espera y tablero multijugador. ssr: false. */
export default function MatchPage({ matchId }: { matchId: string }) {
  const valid = isMatchId(matchId);
  const identity = useIdentity(matchPath(matchId));
  const session = useMatchSocket(valid ? matchId : null);
  const { state, connection, closeCode, closeReason, gameOver, awaitingReply, rejection, serverError } = session;
  const [flipped, setFlipped] = useState(false);
  const [confirmingResign, setConfirmingResign] = useState(false);

  // Respaldo si el perfil no está disponible: el creador visto en la sala de espera (ver matchSession).
  const myId = identity.status === 'ok' ? identity.userId : session.waitingCreator;
  const me = state ? colorOf(state, myId) : null;

  const running = state?.status === 'in_progress' && !gameOver;
  const now = useNow(running);

  useEffect(() => {
    if (closeCode === CLOSE_UNAUTHORIZED) window.location.replace(loginUrl(matchPath(matchId)));
  }, [closeCode, matchId]);

  if (!valid) {
    return (
      <Shell>
        <div className={CARD}>
          <p role="alert">La dirección de la partida no es válida.</p>
          <a href="/multijugador" className={BTN_PRIMARY}>Crear una partida</a>
        </div>
      </Shell>
    );
  }

  if (!state) {
    const closed = connection === 'closed';
    return (
      <Shell>
        <div className={`${CARD} items-center text-center`}>
          <p role={closed ? 'alert' : 'status'}>{closed ? describeClose(closeCode, closeReason) : 'Conectando con la partida…'}</p>
          {closed && closeCode !== CLOSE_NOT_FOUND && closeCode !== CLOSE_UNAUTHORIZED && (
            <button type="button" onClick={session.reconnect} className={BTN_PRIMARY}>
              Reintentar conexión
            </button>
          )}
          {closed && closeCode === CLOSE_NOT_FOUND && (
            <a href={invitePath(matchId)} className={BTN_PRIMARY}>Abrir como invitación</a>
          )}
        </div>
      </Shell>
    );
  }

  const finished = state.status === 'finished' || gameOver !== null;
  const waiting = state.status === 'waiting' && !finished;
  const base: Color = me ?? 'white';
  const orientation: Color = flipped ? opposite(base) : base;
  const myTurn = canMove(session, me);
  const opponent = me ? opposite(me) : null;
  const label = (color: Color) => (me === null ? (state.participants.some((p) => p.color === color) ? 'Jugador' : '—') : color === me ? 'Tú' : 'Rival');
  const offer = state.drawOffer;
  const busy = awaitingReply || connection !== 'open';

  const rounds: string[][] = [];
  for (const move of state.moves) {
    if (move.ply % 2 === 1) rounds.push([move.san]);
    else rounds[rounds.length - 1]?.push(move.san);
  }

  const top: Color = orientation === 'white' ? 'black' : 'white';
  const clockOf = (color: Color) => remainingMs(state.clocks, state.turn, finished ? 'finished' : state.status, color, now);

  return (
    <Shell>
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        <div className="lg:col-span-7 flex flex-col items-center gap-space-sm">
          <div className="w-full max-w-[560px]">
            <PlayerRow color={top} label={label(top)} ms={clockOf(top)} active={running && state.turn === top} />
          </div>
          <ChessBoard
            fen={state.fen}
            legalMoves={state.legalMoves}
            orientation={orientation}
            lastMove={session.lastMove}
            disabled={!myTurn}
            onMove={session.sendMove}
          />
          <div className="w-full max-w-[560px]">
            <PlayerRow color={opposite(top)} label={label(opposite(top))} ms={clockOf(opposite(top))} active={running && state.turn !== top} />
          </div>
          <button type="button" onClick={() => setFlipped(!flipped)} className={BTN_NEUTRAL}>
            <span className="material-symbols-outlined text-[16px]">autorenew</span>
            Girar tablero
          </button>
        </div>

        <aside className="lg:col-span-5 flex flex-col gap-space-sm">
          <div className={CARD}>
            <div className="flex items-center justify-between gap-space-sm">
              <h1 className="font-headline-sm text-headline-sm text-on-surface">Partida online</h1>
              <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary font-label-sm text-label-sm uppercase tracking-wider whitespace-nowrap">
                {state.timeControl ? `${state.timeControl.minutes} min` : 'Sin reloj'} · {state.visibility === 'shared' ? 'Compartida' : 'Privada'}
              </span>
            </div>

            {me ? (
              <p className="font-body-sm text-body-sm text-on-surface-variant">
                Juegas con <strong className="text-on-surface">{COLOR_LABEL[me].toLowerCase()}</strong>
              </p>
            ) : (
              identity.status === 'unknown' && (
                <p role="alert" className={ALERT}>
                  No se pudo identificar tu usuario porque tu perfil no está disponible. Puedes ver la partida, pero no mover. Recarga en
                  unos segundos.
                </p>
              )
            )}

            {finished ? (
              <div className="p-space-sm rounded-xl bg-secondary-container text-on-secondary-fixed flex items-center gap-space-xs" role="status">
                <span className="material-symbols-outlined text-[20px]">flag</span>
                <span className="font-label-lg text-label-lg">{describeResult(state, gameOver, me)}</span>
              </div>
            ) : waiting ? null : (
              <div className="flex items-center gap-space-xs" aria-live="polite">
                <span className={`w-4 h-4 rounded-full border border-outline ${state.turn === 'white' ? 'bg-[#fdf6ea]' : 'bg-[#2a170c]'}`}></span>
                <span className="font-label-lg text-label-lg text-on-surface">
                  Turno: {COLOR_LABEL[state.turn]}
                  {me && (state.turn === me ? ' (tú)' : ' (rival)')}
                </span>
                {running && clockOf(state.turn) === 0 && (
                  <span className="font-body-sm text-body-sm text-on-surface-variant">· esperando confirmación del servidor</span>
                )}
              </div>
            )}

            {!finished && !waiting && session.opponentOnline !== null && (
              <p className={`font-body-sm text-body-sm ${session.opponentOnline ? 'text-secondary' : 'text-error'}`}>
                {session.opponentOnline
                  ? 'Tu rival está conectado.'
                  : `Tu rival se desconectó.${
                      session.opponentDeadline
                        ? ` Si no vuelve antes de las ${new Date(session.opponentDeadline).toLocaleTimeString()}, perderá por abandono.`
                        : ''
                    }`}
              </p>
            )}

            {connection === 'reconnecting' && (
              <p role="status" className={ALERT}>
                Reconectando… (intento {session.retries})
              </p>
            )}
            {connection === 'closed' && !finished && (
              <div role="alert" className={ALERT}>
                {describeClose(closeCode, closeReason)}
                {closeCode !== CLOSE_NOT_FOUND && closeCode !== CLOSE_UNAUTHORIZED && (
                  <button type="button" onClick={session.reconnect} className={`${BTN_NEUTRAL} mt-space-xs`}>
                    Reconectar
                  </button>
                )}
              </div>
            )}
            {rejection && (
              <p role="alert" className={ALERT}>
                Jugada rechazada: {rejection.message || rejection.code}
              </p>
            )}
            {serverError && (
              <p role="alert" className={ALERT}>
                {serverError.code === 'NOT_YOUR_TURN' ? 'No es tu turno.' : serverError.message || serverError.code}
              </p>
            )}
          </div>

          {waiting && <InviteBox matchId={matchId} />}

          {!finished && !waiting && me && (
            <div className={CARD}>
              <h2 className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant">Tablas y abandono</h2>
              {offer === null && (
                <button type="button" disabled={busy} onClick={() => session.send({ type: 'draw_offer' })} className={BTN_NEUTRAL}>
                  <span className="material-symbols-outlined text-[18px]">handshake</span>
                  Ofrecer tablas
                </button>
              )}
              {offer === me && (
                <div className="flex flex-col gap-space-xs">
                  <p className="font-body-sm text-body-sm">Ofreciste tablas. Esperando respuesta del rival…</p>
                  <button type="button" disabled={busy} onClick={() => session.send({ type: 'draw_cancel' })} className={BTN_NEUTRAL}>
                    Retirar oferta
                  </button>
                </div>
              )}
              {offer === opponent && (
                <div className="flex flex-col gap-space-xs" role="alert">
                  <p className="font-label-lg text-label-lg">Tu rival ofrece tablas.</p>
                  <div className="flex gap-space-xs">
                    <button type="button" disabled={busy} onClick={() => session.send({ type: 'draw_accept' })} className={`flex-1 ${BTN_PRIMARY}`}>
                      Aceptar
                    </button>
                    <button type="button" disabled={busy} onClick={() => session.send({ type: 'draw_decline' })} className={`flex-1 ${BTN_NEUTRAL}`}>
                      Rechazar
                    </button>
                  </div>
                </div>
              )}
              {session.drawNotice && offer === null && (
                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  {session.drawNotice === 'declined' ? 'La oferta de tablas fue rechazada.' : 'La oferta de tablas fue retirada.'}
                </p>
              )}

              {confirmingResign ? (
                <div className="flex gap-space-xs">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      session.send({ type: 'resign' });
                      setConfirmingResign(false);
                    }}
                    className={`flex-1 ${BTN} bg-error text-on-error hover:opacity-90`}
                  >
                    Confirmar rendición
                  </button>
                  <button type="button" onClick={() => setConfirmingResign(false)} className={`flex-1 ${BTN_NEUTRAL}`}>
                    Seguir jugando
                  </button>
                </div>
              ) : (
                <button type="button" disabled={busy} onClick={() => setConfirmingResign(true)} className={BTN_NEUTRAL}>
                  <span className="material-symbols-outlined text-[18px]">flag</span>
                  Rendirse
                </button>
              )}
            </div>
          )}

          <div className={CARD}>
            <h2 className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant">Jugadas</h2>
            {rounds.length === 0 ? (
              <p className="font-body-sm text-body-sm text-on-surface-variant">Aún no hay jugadas.</p>
            ) : (
              <ol className="max-h-56 overflow-y-auto font-mono text-[13px] text-on-surface" aria-label="Historial de jugadas">
                {rounds.map(([white, black], index) => (
                  <li key={index} className="grid grid-cols-[2.5rem_1fr_1fr] py-0.5">
                    <span className="text-on-surface-variant">{index + 1}.</span>
                    <span>{white}</span>
                    <span>{black}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>

          {finished && (
            <div className="flex gap-space-xs">
              <a href="/multijugador" className={`flex-1 ${BTN_PRIMARY}`}>
                <span className="material-symbols-outlined text-[18px]">add</span>
                Nueva partida online
              </a>
              <a href="/" className={`flex-1 ${BTN_NEUTRAL}`}>
                Inicio
              </a>
            </div>
          )}
        </aside>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased">
      <AccountNav />
      <main className="px-gutter-mobile md:px-margin py-space-lg">{children}</main>
    </div>
  );
}
