import { useState } from 'react';
import PlayChess from '../game/PlayChess';
import type { GameMode } from '../game/types';

type GameType = 'chess' | 'go' | 'shogi';
type DashboardStep = 'games' | 'mode';

const GAMES: { type: GameType; icon: string; title: string; description: string; badge: string; badgeClass: string; iconClass: string }[] = [
  {
    type: 'chess',
    icon: 'token',
    title: 'Ajedrez Clásico',
    description: 'Dominio posicional, sincronía de piezas y cálculo de rupturas.',
    badge: 'Occidente',
    badgeClass: 'bg-primary/10 text-primary',
    iconClass: 'bg-primary/10 text-primary'
  },
  {
    type: 'go',
    icon: 'radio_button_checked',
    title: 'Go (Weiqi / Baduk)',
    description: 'Construye territorio en 19x19, 13x13 o 9x9. Vida, muerte y ojos.',
    badge: 'Oriente',
    badgeClass: 'bg-tertiary/10 text-tertiary',
    iconClass: 'bg-tertiary/10 text-tertiary'
  },
  {
    type: 'shogi',
    icon: 'change_circle',
    title: 'Shogi',
    description: 'Ajedrez japonés con reingreso de capturas. Partidas dinámicas sin tablas.',
    badge: 'Japón',
    badgeClass: 'bg-secondary/10 text-secondary',
    iconClass: 'bg-secondary/10 text-secondary'
  }
];

const MODES: { mode: GameMode; icon: string; title: string; description: string }[] = [
  {
    mode: 'local',
    icon: 'group',
    title: 'Partida Local',
    description: 'Dos jugadores en este mismo dispositivo, por turnos.',
  },
  {
    mode: 'vs_bot',
    icon: 'smart_toy',
    title: 'Contra Botcito',
    description: 'Juega contra el motor y elige su nivel de dificultad.',
  },
];

interface DashboardProps {
  user: { userId: string; username: string };
  token: string;
  onLogout: () => void;
}

export default function Dashboard({ user, token, onLogout }: DashboardProps) {
  const [step, setStep] = useState<DashboardStep>('games');
  const [selectedGame, setSelectedGame] = useState<GameType | null>(null);
  const [selectedMode, setSelectedMode] = useState<GameMode | null>(null);

  const handleGameSelect = (gameType: GameType) => {
    if (gameType !== 'chess') {
      alert(`${GAMES.find(g => g.type === gameType)?.title} - Próximamente disponible en el prototipo.`);
      return;
    }
    setSelectedGame(gameType);
    setStep('mode');
  };

  const handleModeSelect = (mode: GameMode) => {
    setSelectedMode(mode);
  };

  const handleBackToGames = () => {
    setStep('games');
    setSelectedGame(null);
    setSelectedMode(null);
  };

  const handleExitGame = () => {
    setSelectedGame(null);
    setSelectedMode(null);
    setStep('games');
  };

  // Si seleccionamos ajedrez y modo, mostramos PlayChess
  if (selectedGame === 'chess' && selectedMode !== null) {
    return (
      <PlayChess
        token={token}
        onUnauthorized={onLogout}
        preselectedMode={selectedMode}
        onExit={handleExitGame}
      />
    );
  }

  // Paso 2: Selección de modo (después de elegir Ajedrez)
  if (step === 'mode' && selectedGame === 'chess') {
    return (
      <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased">
        <header className="fixed top-0 left-0 right-0 z-50 bg-surface/90 backdrop-blur-md shadow-[0_1px_8px_rgba(76,56,36,0.05)]">
          <div className="h-20 w-full px-gutter md:px-margin flex items-center justify-between">
            <div className="flex items-center gap-space-md">
              <button
                onClick={handleBackToGames}
                className="px-space-md py-space-xs rounded-lg bg-surface-container-high text-on-surface font-label-lg text-label-lg hover:bg-surface-container-highest transition-colors cursor-pointer flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-[18px]">arrow_back</span>
                <span>Atrás</span>
              </button>
            </div>
            <div className="flex items-center gap-space-sm md:gap-space-md">
              <span className="hidden sm:inline-flex font-label-lg text-label-lg text-on-surface">Hola, {user.username}</span>
              <button
                onClick={onLogout}
                className="px-space-md py-space-xs rounded-lg bg-surface-container-high text-on-surface font-label-lg text-label-lg shadow-sm hover:bg-error-container transition-colors cursor-pointer"
              >
                Salir
              </button>
              <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary">
                <span className="material-symbols-outlined text-[18px]">person</span>
              </div>
            </div>
          </div>
        </header>

        <main className="w-full pt-20 pb-space-xl px-gutter md:px-margin">
          <div className="max-w-2xl mx-auto flex flex-col gap-space-xl">

            <div className="flex items-center gap-space-md mb-space-lg">
              <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                <span className="material-symbols-outlined text-[24px]">token</span>
              </div>
              <span className="font-label-sm text-label-sm uppercase tracking-widest text-primary font-bold">Ajedrez</span>
            </div>

            <div className="text-center mb-space-lg">
              <h1 className="font-headline-lg text-headline-lg text-on-surface mb-2">¿Cómo quieres jugar?</h1>
              <p className="font-body-md text-body-md text-on-surface-variant">
                Elige el modo de partida.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-lg">
              {MODES.map((modeOption) => (
                <button
                  key={modeOption.mode}
                  onClick={() => handleModeSelect(modeOption.mode)}
                  className="p-space-xl rounded-2xl bg-surface-container-low border border-outline-variant/40 hover:border-primary/50 hover:shadow-lg transition-all duration-300 flex flex-col items-center text-center cursor-pointer group"
                >
                  <div className="w-16 h-16 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-space-md group-hover:scale-110 transition-transform">
                    <span className="material-symbols-outlined text-[32px]">{modeOption.icon}</span>
                  </div>
                  <h3 className="font-headline-md text-headline-md text-on-surface mb-1">{modeOption.title}</h3>
                  <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed text-center">
                    {modeOption.description}
                  </p>
                </button>
              ))}
            </div>

          </div>
        </main>

        <footer className="w-full bg-surface-container-low pt-space-xl pb-space-lg shadow-[0_-1px_6px_rgba(76,56,36,0.03)]">
          <div className="w-full px-gutter md:px-margin max-w-7xl mx-auto flex flex-col gap-space-lg">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-space-sm pt-space-md text-on-surface-variant font-body-sm text-body-sm">
              <p>© 2026 Insightful Games. Todos los derechos reservados.</p>
              <div className="flex items-center gap-space-md">
                <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#" onClick={(e) => {e.preventDefault(); alert("Términos de servicio del Prototipo 1");}}>Términos de Servicio</a>
                <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#" onClick={(e) => {e.preventDefault(); alert("Política de privacidad");}}>Privacidad</a>
                <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#" onClick={(e) => {e.preventDefault(); alert("Desarrollado para la asignatura Arquitectura de Software 2026-II");}}>Créditos</a>
              </div>
            </div>
          </div>
        </footer>
      </div>
    );
  }

  // Paso 1: Selección de juego
  return (
    <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-surface/90 backdrop-blur-md shadow-[0_1px_8px_rgba(76,56,36,0.05)]">
        <div className="h-20 w-full px-gutter md:px-margin flex items-center justify-between">
          <div className="flex items-center gap-space-md">
            <a className="flex items-center gap-space-sm cursor-pointer" href="#">
              <img
                alt="Insightful Games"
                className="h-9 md:h-10 w-auto object-contain"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuC5cvnzUVCsIV5Y9kK200mfZ5t6fi3ewr4yEeIF3NtiwPjOGifuWMGPzThVr0d2FIo3BkkiPz8u-gDL7xhRw8Bat33rEaL0ZHQ4M57zWSAJD5spblm7MH7b1feIKwPNOAYoJN1XWnjOVqBvkYb7mzaTKxc_31Gx5bntJwv7cc1VO-WXObKhWKz7KluRC4cNrMSGyD_pIMh5QEsMLZ9ZG_7hAoezhYORpVsHz8RTG_gVOTmH3QUTTgNsfGIAELq31GgLpT8"
              />
            </a>
          </div>
          <div className="flex items-center gap-space-sm md:gap-space-md">
            <span className="hidden sm:inline-flex font-label-lg text-label-lg text-on-surface">Hola, {user.username}</span>
            <button
              onClick={onLogout}
              className="px-space-md py-space-xs rounded-lg bg-surface-container-high text-on-surface font-label-lg text-label-lg shadow-sm hover:bg-error-container transition-colors cursor-pointer"
            >
              Salir
            </button>
            <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary">
              <span className="material-symbols-outlined text-[18px]">person</span>
            </div>
          </div>
        </div>
      </header>

      <main className="w-full pt-20 pb-space-xl px-gutter md:px-margin">
        <div className="max-w-4xl mx-auto flex flex-col gap-space-xl">

          {/* Header del Dashboard */}
          <div className="text-center">
            <span className="font-label-sm text-label-sm uppercase tracking-widest text-primary font-bold">Insightful Games</span>
            <h1 className="font-headline-lg text-headline-lg text-on-surface mt-1">
              Elige tu juego milenario
            </h1>
            <p className="font-body-md text-body-md text-on-surface-variant mt-1">
              Selecciona a qué juego quieres jugar.
            </p>
          </div>

          {/* Tarjetas de juego */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-space-lg">
            {GAMES.map((game) => (
              <button
                key={game.type}
                onClick={() => handleGameSelect(game.type)}
                className="flex flex-col rounded-2xl bg-surface-container-low p-space-lg shadow-md hover:shadow-xl transition-all duration-300 relative group overflow-hidden cursor-pointer"
                disabled={game.type !== 'chess'}
              >
                <div className={`w-12 h-12 rounded-xl ${game.iconClass} flex items-center justify-center mb-space-md group-hover:scale-110 transition-transform`}>
                  <span className="material-symbols-outlined text-[28px]">{game.icon}</span>
                </div>
                <span className={`font-label-sm text-label-sm font-bold uppercase tracking-wider ${game.badgeClass}`}>{game.badge}</span>
                <h3 className="font-headline-md text-headline-md text-on-surface mt-1 mb-space-xs">{game.title}</h3>
                <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed mb-space-md flex-1">
                  {game.description}
                </p>
                {game.type !== 'chess' && (
                  <div className="absolute inset-0 bg-surface/80 flex items-center justify-center rounded-2xl">
                    <span className="px-3 py-1.5 rounded-full bg-primary/10 text-primary text-xs font-semibold">Próximamente</span>
                  </div>
                )}
                <div className="mt-auto pt-space-md border-t border-outline-variant/30">
                  <span className="w-full py-space-xs rounded-lg bg-surface-container-highest text-on-surface font-label-md text-label-md hover:bg-primary hover:text-on-primary transition-colors flex items-center justify-center gap-1 shadow-sm block opacity-60">
                    {game.type === 'chess' ? 'Jugar' : 'No disponible'}
                    <span className="material-symbols-outlined text-[16px]">chevron_right</span>
                  </span>
                </div>
              </button>
            ))}
          </div>

        </div>
      </main>

      {/* Footer */}
      <footer className="w-full bg-surface-container-low pt-space-xl pb-space-lg shadow-[0_-1px_6px_rgba(76,56,36,0.03)]">
        <div className="w-full px-gutter md:px-margin max-w-7xl mx-auto flex flex-col gap-space-lg">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-space-sm pt-space-md text-on-surface-variant font-body-sm text-body-sm">
            <p>© 2026 Insightful Games. Todos los derechos reservados.</p>
            <div className="flex items-center gap-space-md">
              <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#" onClick={(e) => {e.preventDefault(); alert("Términos de servicio del Prototipo 1");}}>Términos de Servicio</a>
              <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#" onClick={(e) => {e.preventDefault(); alert("Política de privacidad");}}>Privacidad</a>
              <a className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors" href="#" onClick={(e) => {e.preventDefault(); alert("Desarrollado para la asignatura Arquitectura de Software 2026-II");}}>Créditos</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}