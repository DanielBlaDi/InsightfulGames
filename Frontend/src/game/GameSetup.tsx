import { useState } from 'react';
import { MAX_BOT_LEVEL, MIN_BOT_LEVEL } from './types';
import type { Color, CreateGameRequest, GameMode } from './types';

const MODES: { mode: GameMode; icon: string; title: string; description: string }[] = [
  {
    mode: 'local',
    icon: 'group',
    title: 'Partida local',
    description: 'Dos jugadores en este mismo dispositivo, por turnos.',
  },
  {
    mode: 'vs_bot',
    icon: 'smart_toy',
    title: 'Contra Botcito',
    description: 'Juega contra el motor y elige su nivel de dificultad.',
  },
];

const COLORS: { color: Color; label: string; hint: string; swatch: string }[] = [
  { color: 'white', label: 'Blancas', hint: 'Mueves primero', swatch: 'bg-[#fdf6ea]' },
  { color: 'black', label: 'Negras', hint: 'Botcito mueve primero', swatch: 'bg-[#2a170c]' },
];

const DEFAULT_LEVEL = 8;

const optionClass = (active: boolean) =>
  `text-left p-space-md rounded-2xl border transition-all cursor-pointer disabled:cursor-not-allowed ${
    active
      ? 'bg-primary/10 border-primary shadow-sm'
      : 'bg-surface-container-low border-outline-variant/40 hover:border-outline'
  }`;

interface GameSetupProps {
  loading: boolean;
  error: string | null;
  onStart: (request: CreateGameRequest) => void;
  /** Si se pasa, se ofrece salir del módulo (por ejemplo, volver a la página de inicio). */
  onExit?: () => void;
}

/** Formulario de configuración: decide el cuerpo de POST /games, pero no hace la llamada. */
export default function GameSetup({ loading, error, onStart, onExit }: GameSetupProps) {
  const [mode, setMode] = useState<GameMode>('local');
  const [level, setLevel] = useState(DEFAULT_LEVEL);
  const [playerColor, setPlayerColor] = useState<Color>('white');

  const request: CreateGameRequest = mode === 'local' ? { mode } : { mode, level, playerColor };

  return (
    <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased px-gutter-mobile md:px-margin py-space-xl">
      <form
        className="max-w-2xl mx-auto flex flex-col gap-space-lg"
        onSubmit={(event) => {
          event.preventDefault();
          if (!loading) onStart(request);
        }}
      >
        <header className="flex flex-col gap-space-xs">
          {onExit && (
            <button
              type="button"
              onClick={onExit}
              className="self-start mb-space-sm font-label-lg text-label-lg text-on-surface-variant hover:text-on-surface transition-colors flex items-center gap-1 cursor-pointer"
            >
              <span className="material-symbols-outlined text-[18px]">arrow_back</span>
              Volver al inicio
            </button>
          )}
          <span className="font-label-sm text-label-sm uppercase tracking-widest text-primary">Ajedrez</span>
          <h1 className="font-headline-lg text-headline-lg text-on-surface">Configura tu partida</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Elige cómo quieres jugar. Podrás volver a esta pantalla cuando quieras.
          </p>
        </header>

        <fieldset disabled={loading} className="flex flex-col gap-space-sm">
          <legend className="font-label-lg text-label-lg text-on-surface mb-space-sm">Modo de juego</legend>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-sm">
            {MODES.map((option) => (
              <button
                key={option.mode}
                type="button"
                aria-pressed={mode === option.mode}
                onClick={() => setMode(option.mode)}
                className={optionClass(mode === option.mode)}
              >
                <span className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-space-sm">
                  <span className="material-symbols-outlined text-[24px]">{option.icon}</span>
                </span>
                <span className="block font-headline-sm text-headline-sm text-on-surface">{option.title}</span>
                <span className="block font-body-sm text-body-sm text-on-surface-variant mt-1">
                  {option.description}
                </span>
              </button>
            ))}
          </div>
        </fieldset>

        {mode === 'vs_bot' && (
          <fieldset
            disabled={loading}
            className="p-space-md rounded-2xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-space-md"
          >
            <legend className="sr-only">Opciones contra Botcito</legend>

            <div className="flex flex-col gap-space-xs">
              <label htmlFor="bot-level" className="flex items-baseline justify-between gap-space-sm">
                <span className="font-label-lg text-label-lg text-on-surface">Nivel de dificultad</span>
                <span className="font-headline-sm text-headline-sm text-primary">
                  {level}
                  <span className="font-body-sm text-body-sm text-on-surface-variant"> de {MAX_BOT_LEVEL}</span>
                </span>
              </label>
              <input
                id="bot-level"
                type="range"
                min={MIN_BOT_LEVEL}
                max={MAX_BOT_LEVEL}
                step={1}
                value={level}
                onChange={(event) => setLevel(Number(event.target.value))}
                className="w-full accent-primary cursor-pointer"
              />
              <div className="flex justify-between font-body-sm text-body-sm text-on-surface-variant">
                <span>{MIN_BOT_LEVEL} · más fácil</span>
                <span>{MAX_BOT_LEVEL} · más difícil</span>
              </div>
            </div>

            <div className="flex flex-col gap-space-xs">
              <span className="font-label-lg text-label-lg text-on-surface">Tus piezas</span>
              <div className="grid grid-cols-2 gap-space-sm">
                {COLORS.map((option) => (
                  <button
                    key={option.color}
                    type="button"
                    aria-pressed={playerColor === option.color}
                    onClick={() => setPlayerColor(option.color)}
                    className={`${optionClass(playerColor === option.color)} flex items-center gap-space-sm`}
                  >
                    <span className={`w-7 h-7 rounded-full border border-outline shrink-0 ${option.swatch}`}></span>
                    <span>
                      <span className="block font-label-lg text-label-lg text-on-surface">{option.label}</span>
                      <span className="block font-body-sm text-body-sm text-on-surface-variant">{option.hint}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </fieldset>
        )}

        <section
          aria-live="polite"
          className="p-space-md rounded-2xl bg-surface-container border border-outline-variant/30 flex flex-col gap-space-xs"
        >
          <h2 className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant">
            Tu configuración
          </h2>
          <dl className="grid grid-cols-[auto_1fr] gap-x-space-md gap-y-1 font-body-md text-body-md">
            <dt className="text-on-surface-variant">Modo</dt>
            <dd className="text-on-surface font-semibold">
              {request.mode === 'local' ? 'Local, dos jugadores' : 'Contra Botcito'}
            </dd>
            {request.mode === 'vs_bot' && (
              <>
                <dt className="text-on-surface-variant">Nivel</dt>
                <dd className="text-on-surface font-semibold">
                  {request.level} de {MAX_BOT_LEVEL}
                </dd>
                <dt className="text-on-surface-variant">Tus piezas</dt>
                <dd className="text-on-surface font-semibold">
                  {request.playerColor === 'white' ? 'Blancas' : 'Negras'}
                </dd>
              </>
            )}
          </dl>
        </section>

        {error && (
          <div
            role="alert"
            className="p-space-sm rounded-xl bg-error-container text-on-error-container font-body-sm text-body-sm flex items-start gap-space-xs"
          >
            <span className="material-symbols-outlined text-[18px]">error</span>
            <span>{error}</span>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="px-space-lg py-space-sm rounded-xl bg-primary text-on-primary font-label-lg text-label-lg shadow-md hover:bg-primary-container transition-all flex items-center justify-center gap-space-xs cursor-pointer disabled:opacity-70 disabled:cursor-wait"
        >
          <span className={`material-symbols-outlined text-[18px] ${loading ? 'animate-spin' : ''}`}>
            {loading ? 'progress_activity' : 'play_arrow'}
          </span>
          {loading ? 'Creando partida…' : 'Iniciar partida'}
        </button>
      </form>
    </div>
  );
}
