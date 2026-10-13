import { useEffect, useEffectEvent, useState } from 'react';
import ChessBoard from './ChessBoard';
import { CLOSE_GAME_NOT_FOUND, CLOSE_UNAUTHORIZED } from './session';
import type { GameSession } from './session';
import type { Color, EndReason, GameState } from './types';

const COLOR_LABEL: Record<Color, string> = { white: 'Blancas', black: 'Negras' };

const REASON_LABEL: Record<EndReason, string> = {
  checkmate: 'por jaque mate',
  stalemate: 'por ahogado',
  resignation: 'por abandono',
  draw: '',
};

function describeResult(state: GameState): string {
  if (state.result === null) return 'Partida finalizada';
  const reason = state.endReason ? REASON_LABEL[state.endReason] : '';
  const outcome = state.result === 'draw' ? 'Tablas' : `Ganan las ${COLOR_LABEL[state.result].toLowerCase()}`;
  return `${outcome} ${reason}`.trim();
}

function describeClose(code: number | null): string {
  if (code === CLOSE_UNAUTHORIZED) return 'Tu sesión venció. Inicia sesión de nuevo.';
  if (code === CLOSE_GAME_NOT_FOUND) return 'La partida no existe o no te pertenece.';
  return 'Se perdió la conexión con la partida.';
}

interface GamePageProps {
  session: GameSession;
  /** El contrato pide volver al login ante un token inválido; la navegación la decide quien monta la pantalla. */
  onUnauthorized?: () => void;
  /** Si se pasa, se ofrece salir de la partida. Salir no la abandona: sigue en curso en el servidor. */
  onExit?: () => void;
}

const EXIT_BUTTON =
  'py-space-xs px-space-md rounded-lg bg-surface-container-high text-on-surface font-label-lg text-label-lg hover:bg-surface-container-highest transition-colors flex items-center justify-center gap-1 cursor-pointer';

export default function GamePage({ session, onUnauthorized, onExit }: GamePageProps) {
  const {
    connection,
    closeCode,
    state,
    lastMove,
    botThinking,
    awaitingReply,
    rejection,
    serverError,
    sendMove,
    resign,
    reconnect,
  } = session;
  const [flipped, setFlipped] = useState(false);
  const [confirmingResign, setConfirmingResign] = useState(false);
  const disconnected = connection === 'closed';
  // Un cierre por token o por partida ajena no se arregla reconectando.
  const canReconnect = disconnected && closeCode !== CLOSE_UNAUTHORIZED && closeCode !== CLOSE_GAME_NOT_FOUND;

  // Una sola llamada por cierre, aunque quien monta la pantalla pase un callback nuevo en cada render.
  const notifyUnauthorized = useEffectEvent(() => onUnauthorized?.());
  useEffect(() => {
    if (closeCode === CLOSE_UNAUTHORIZED) notifyUnauthorized();
  }, [closeCode]);

  if (!state) {
    return (
      <div className="w-full min-h-screen bg-background flex flex-col items-center justify-center gap-space-md px-gutter-mobile text-center font-body-md text-body-md text-on-surface-variant">
        {disconnected ? describeClose(closeCode) : 'Conectando con la partida…'}
        {canReconnect && (
          <button type="button" onClick={reconnect} className={EXIT_BUTTON}>
            <span className="material-symbols-outlined text-[18px]">refresh</span>
            Reintentar conexión
          </button>
        )}
        {onExit && (
          <button type="button" onClick={onExit} className={EXIT_BUTTON}>
            <span className="material-symbols-outlined text-[18px]">arrow_back</span>
            Volver a la configuración
          </button>
        )}
      </div>
    );
  }

  const finished = state.status === 'finished';
  const vsBot = state.mode === 'vs_bot';
  const botTurn = vsBot && state.turn !== state.playerColor;
  const base: Color = state.playerColor ?? 'white';
  const orientation: Color = flipped ? (base === 'white' ? 'black' : 'white') : base;

  const handleResign = () => {
    // El contrato solo pide `side` en modo local: abandona quien tiene el turno.
    resign(vsBot ? undefined : state.turn);
    setConfirmingResign(false);
  };

  // Jugadas agrupadas por número: [blancas, negras]
  const rounds: string[][] = [];
  for (const move of state.moves) {
    if (move.ply % 2 === 1) rounds.push([move.san]);
    else rounds[rounds.length - 1]?.push(move.san);
  }

  return (
    <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased px-gutter-mobile md:px-margin py-space-lg">
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        <div className="lg:col-span-7 flex flex-col items-center gap-space-sm">
          <ChessBoard
            fen={state.fen}
            legalMoves={state.legalMoves}
            orientation={orientation}
            lastMove={lastMove}
            disabled={finished || botTurn || botThinking || awaitingReply || connection !== 'open'}
            onMove={sendMove}
          />
          <button
            type="button"
            onClick={() => setFlipped(!flipped)}
            className="px-space-sm py-space-xs rounded-lg bg-surface-container font-label-md text-label-md text-on-surface hover:bg-surface-container-high transition-colors flex items-center gap-1 shadow-sm cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px]">autorenew</span>
            Girar tablero
          </button>
        </div>

        <aside className="lg:col-span-5 flex flex-col gap-space-sm">
          <div className="p-space-md rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm flex flex-col gap-space-sm">
            <div className="flex items-center justify-between gap-space-sm">
              <h1 className="font-headline-sm text-headline-sm text-on-surface">
                {vsBot ? 'Partida contra Botcito' : 'Partida local'}
              </h1>
              <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary font-label-sm text-label-sm uppercase tracking-wider whitespace-nowrap">
                {vsBot ? `Nivel ${state.botLevel}` : '2 jugadores'}
              </span>
            </div>

            {finished ? (
              <div className="p-space-sm rounded-xl bg-secondary-container text-on-secondary-fixed flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-[20px]">flag</span>
                <span className="font-label-lg text-label-lg">{describeResult(state)}</span>
              </div>
            ) : (
              <div className="flex items-center gap-space-xs" aria-live="polite">
                <span
                  className={`w-4 h-4 rounded-full border border-outline ${
                    state.turn === 'white' ? 'bg-[#fdf6ea]' : 'bg-[#2a170c]'
                  }`}
                ></span>
                <span className="font-label-lg text-label-lg text-on-surface">
                  {botThinking
                    ? 'Botcito está pensando…'
                    : `Turno: ${COLOR_LABEL[state.turn]}${
                        vsBot ? (botTurn ? ' (Botcito)' : ' (tú)') : ''
                      }`}
                </span>
              </div>
            )}

            <p className="font-body-sm text-body-sm text-on-surface-variant">
              Estado: <strong className="text-on-surface">{finished ? 'Finalizada' : 'En curso'}</strong>
              {vsBot && state.playerColor && <> · Juegas con {COLOR_LABEL[state.playerColor].toLowerCase()}</>}
            </p>

            {disconnected && !finished && (
              <div
                role="alert"
                className="p-space-sm rounded-xl bg-error-container text-on-error-container font-body-sm text-body-sm"
              >
                {describeClose(closeCode)}
              </div>
            )}

            {serverError && (
              <div
                role="alert"
                className="p-space-sm rounded-xl bg-error-container text-on-error-container font-body-sm text-body-sm"
              >
                <strong>{serverError.code}</strong> · {serverError.message}
                {!finished && (
                  <p className="mt-1">
                    {botTurn
                      ? 'Botcito no pudo jugar. La partida sigue como estaba; puedes reintentar.'
                      : 'La partida sigue como estaba; puedes repetir tu jugada.'}
                  </p>
                )}
              </div>
            )}

            {!finished && (canReconnect || (serverError && botTurn)) && (
              <button type="button" onClick={reconnect} className={EXIT_BUTTON}>
                <span className="material-symbols-outlined text-[18px]">refresh</span>
                {canReconnect ? 'Reintentar conexión' : 'Reintentar turno de Botcito'}
              </button>
            )}

            {rejection && (
              <div
                role="alert"
                className="p-space-sm rounded-xl bg-error-container text-on-error-container font-body-sm text-body-sm"
              >
                <strong>{rejection.code}</strong> · {rejection.message}
              </div>
            )}
          </div>

          <div className="p-space-md rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm">
            <h2 className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant mb-space-xs">
              Jugadas
            </h2>
            {rounds.length === 0 ? (
              <p className="font-body-sm text-body-sm text-on-surface-variant">Aún no hay jugadas.</p>
            ) : (
              <ol className="max-h-56 overflow-y-auto font-mono text-[13px] text-on-surface">
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

          {!finished &&
            !disconnected &&
            (confirmingResign ? (
              <div className="flex gap-space-xs">
                <button
                  type="button"
                  onClick={handleResign}
                  className="flex-1 py-space-xs rounded-lg bg-error text-on-error font-label-lg text-label-lg hover:opacity-90 transition-opacity cursor-pointer"
                >
                  Confirmar abandono
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingResign(false)}
                  className="flex-1 py-space-xs rounded-lg bg-surface-container-high text-on-surface font-label-lg text-label-lg hover:bg-surface-container-highest transition-colors cursor-pointer"
                >
                  Seguir jugando
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmingResign(true)}
                className="py-space-xs rounded-lg bg-surface-container-high text-on-surface font-label-lg text-label-lg hover:bg-surface-container-highest transition-colors flex items-center justify-center gap-1 cursor-pointer"
              >
                <span className="material-symbols-outlined text-[18px]">flag</span>
                Abandonar{vsBot ? '' : ` (${COLOR_LABEL[state.turn].toLowerCase()})`}
              </button>
            ))}

          {onExit && (
            <button type="button" onClick={onExit} className={EXIT_BUTTON}>
              <span className="material-symbols-outlined text-[18px]">{finished ? 'add' : 'arrow_back'}</span>
              {finished ? 'Nueva partida' : 'Volver a la configuración'}
            </button>
          )}
        </aside>
      </div>
    </div>
  );
}
