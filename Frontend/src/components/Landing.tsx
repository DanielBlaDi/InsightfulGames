import { useState, useEffect } from 'react';

interface LandingProps {
  onLogin: () => void;
  onLogout?: () => void;
  user?: { userId: string; username: string } | null;
}

export default function Landing({ onLogin, onLogout, user }: LandingProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeBoard, setActiveBoard] = useState<'chess' | 'go' | 'shogi'>('chess');

  const openBoardModal = (gameKey: 'chess' | 'go' | 'shogi') => {
    setActiveBoard(gameKey);
    setIsModalOpen(true);
    document.body.style.overflow = 'hidden';
  };

  const closeBoardModal = () => {
    setIsModalOpen(false);
    document.body.style.overflow = '';
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isModalOpen) {
        closeBoardModal();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isModalOpen]);

  const boardMetadata = {
    chess: {
      title: 'Tablero de Ajedrez Clásico',
      badge: 'Táctica Posicional',
      badgeClass: 'bg-primary/10 text-primary',
      subtitle: 'Interactivo • Tutor IA pedagógico con retroalimentación en lenguaje natural',
      icon: 'token',
      iconClass: 'bg-primary/10 text-primary'
    },
    go: {
      title: 'Tablero Goban de Go (Weiqi)',
      badge: 'Territorio & Vida',
      badgeClass: 'bg-tertiary/10 text-tertiary',
      subtitle: 'Interactivo • Tutor IA con lectura espacial de ojos y libertades',
      icon: 'radio_button_checked',
      iconClass: 'bg-tertiary/10 text-tertiary'
    },
    shogi: {
      title: 'Tablero Tradicional de Shogi',
      badge: 'Ciclo & Ascenso',
      badgeClass: 'bg-secondary/10 text-secondary',
      subtitle: 'Interactivo • Tutor IA con sistema de reintroducción de capturas',
      icon: 'change_circle',
      iconClass: 'bg-secondary/10 text-secondary'
    }
  };

  return (
    <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased selection:bg-primary-fixed selection:text-on-primary-fixed">
      {/* HEADER */}
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
          <nav className="hidden lg:flex items-center gap-space-md">
            <a className="px-space-sm py-space-xs rounded-lg font-label-lg text-label-lg text-on-surface-variant hover:text-on-surface transition-colors" href="#juegos-milenarios">
              Juegos
            </a>
            <a className="px-space-sm py-space-xs rounded-lg font-label-lg text-label-lg text-on-surface-variant hover:text-on-surface transition-colors" href="#filosofia">
              Filosofía &amp; Metodología
            </a>
            <a className="px-space-sm py-space-xs rounded-lg font-label-lg text-label-lg text-on-surface-variant hover:text-on-surface transition-colors" href="#comunidad" onClick={(e) => { e.preventDefault(); alert("¡Comunidad próximamente disponible en el prototipo!"); }}>
              Comunidad
            </a>
          </nav>
          <div className="flex items-center gap-space-sm md:gap-space-md">
            {user ? (
              <>
                <span className="font-label-lg text-label-lg text-on-surface">Hola, {user.username}</span>
                <button
                  onClick={onLogout}
                  className="px-space-md py-space-xs rounded-lg bg-surface-container-high text-on-surface font-label-lg text-label-lg shadow-sm hover:bg-error-container transition-colors cursor-pointer"
                >
                  Salir
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={onLogin}
                  className="hidden sm:inline-flex px-space-md py-space-xs rounded-lg font-label-lg text-label-lg text-on-surface-variant hover:text-on-surface transition-colors cursor-pointer"
                >
                  Iniciar Sesión
                </button>
                <button
                  onClick={onLogin}
                  className="px-space-md py-space-xs rounded-lg bg-primary text-on-primary font-label-lg text-label-lg shadow-sm hover:bg-primary-container transition-colors cursor-pointer"
                >
                  Regístrate
                </button>
              </>
            )}
            <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary">
              <span className="material-symbols-outlined text-[18px]">person</span>
            </div>
          </div>
        </div>
      </header>

      <main className="w-full pt-20 bg-background">
        <div className="flex flex-col w-full selection:bg-primary-fixed selection:text-on-primary-fixed">

          {/* HERO STAGE ANIMADO */}
          <section className="relative w-full overflow-hidden bg-gradient-to-b from-surface via-surface-container-low to-surface px-gutter md:px-margin py-space-xl">
            <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[720px] h-[720px] rounded-full bg-primary-fixed/25 blur-3xl pointer-events-none"></div>
            <div className="absolute top-1/4 -right-24 w-[420px] h-[420px] rounded-full bg-tertiary-fixed/25 blur-3xl pointer-events-none"></div>
            <div className="absolute -bottom-24 -left-20 w-[460px] h-[460px] rounded-full bg-secondary-fixed/30 blur-3xl pointer-events-none"></div>

            <div className="max-w-6xl mx-auto flex flex-col items-center relative z-10">
              <style>{`
                @keyframes orbitEllipseKing {
                  0%   { transform: translate(-50%, -50%) translate(0px, -170px) scale(0.92); z-index: 15; }
                  25%  { transform: translate(-50%, -50%) translate(290px, -30px) scale(1.02); z-index: 25; }
                  50%  { transform: translate(-50%, -50%) translate(150px, 150px) scale(1.10); z-index: 35; }
                  75%  { transform: translate(-50%, -50%) translate(-270px, 40px) scale(0.98); z-index: 25; }
                  100% { transform: translate(-50%, -50%) translate(0px, -170px) scale(0.92); z-index: 15; }
                }
                @keyframes orbitEllipseGo {
                  0%   { transform: translate(-50%, -50%) translate(250px, 90px) scale(1.06); z-index: 30; }
                  25%  { transform: translate(-50%, -50%) translate(-160px, 160px) scale(1.12); z-index: 35; }
                  50%  { transform: translate(-50%, -50%) translate(-290px, -40px) scale(0.96); z-index: 20; }
                  75%  { transform: translate(-50%, -50%) translate(0px, -170px) scale(0.90); z-index: 15; }
                  100% { transform: translate(-50%, -50%) translate(250px, 90px) scale(1.06); z-index: 30; }
                }
                @keyframes orbitEllipseShogi {
                  0%   { transform: translate(-50%, -50%) translate(-270px, -20px) scale(0.96); z-index: 20; }
                  25%  { transform: translate(-50%, -50%) translate(0px, -170px) scale(0.90); z-index: 15; }
                  50%  { transform: translate(-50%, -50%) translate(280px, -20px) scale(1.03); z-index: 25; }
                  75%  { transform: translate(-50%, -50%) translate(100px, 165px) scale(1.12); z-index: 35; }
                  100% { transform: translate(-50%, -50%) translate(-270px, -20px) scale(0.96); z-index: 20; }
                }
                @media (max-width: 640px) {
                  @keyframes orbitEllipseKing {
                    0%   { transform: translate(-50%, -50%) translate(0px, -125px) scale(0.85); z-index: 15; }
                    25%  { transform: translate(-50%, -50%) translate(145px, -20px) scale(0.95); z-index: 25; }
                    50%  { transform: translate(-50%, -50%) translate(75px, 115px) scale(1.02); z-index: 35; }
                    75%  { transform: translate(-50%, -50%) translate(-140px, 30px) scale(0.92); z-index: 25; }
                    100% { transform: translate(-50%, -50%) translate(0px, -125px) scale(0.85); z-index: 15; }
                  }
                  @keyframes orbitEllipseGo {
                    0%   { transform: translate(-50%, -50%) translate(130px, 70px) scale(1.0); z-index: 30; }
                    25%  { transform: translate(-50%, -50%) translate(-80px, 120px) scale(1.05); z-index: 35; }
                    50%  { transform: translate(-50%, -50%) translate(-145px, -30px) scale(0.9); z-index: 20; }
                    75%  { transform: translate(-50%, -50%) translate(0px, -125px) scale(0.85); z-index: 15; }
                    100% { transform: translate(-50%, -50%) translate(130px, 70px) scale(1.0); z-index: 30; }
                  }
                  @keyframes orbitEllipseShogi {
                    0%   { transform: translate(-50%, -50%) translate(-140px, -15px) scale(0.9); z-index: 20; }
                    25%  { transform: translate(-50%, -50%) translate(0px, -125px) scale(0.85); z-index: 15; }
                    50%  { transform: translate(-50%, -50%) translate(140px, -15px) scale(0.98); z-index: 25; }
                    75%  { transform: translate(-50%, -50%) translate(50px, 120px) scale(1.05); z-index: 35; }
                    100% { transform: translate(-50%, -50%) translate(-140px, -15px) scale(0.9); z-index: 20; }
                  }
                }
                .orbit-track-king { animation: orbitEllipseKing 24s cubic-bezier(0.445, 0.05, 0.55, 0.95) infinite; }
                .orbit-track-go { animation: orbitEllipseGo 24s cubic-bezier(0.445, 0.05, 0.55, 0.95) infinite; }
                .orbit-track-shogi { animation: orbitEllipseShogi 24s cubic-bezier(0.445, 0.05, 0.55, 0.95) infinite; }
                .orbit-track:hover, .orbit-track:focus-visible { animation-play-state: paused !important; }
              `}</style>

              {/* STAGE ORBIT */}
              <div className="relative w-full max-w-4xl h-[460px] md:h-[520px] flex items-center justify-center mb-space-lg select-none perspective-[1000px]" id="hero-orbit-stage">
                <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-45" fill="none" viewBox="0 0 800 520">
                  <ellipse className="text-outline-variant" cx="400" cy="260" rx="360" ry="190" stroke="currentColor" strokeDasharray="6 6" strokeWidth="1.2"></ellipse>
                  <ellipse className="text-tertiary-fixed-dim" cx="400" cy="260" rx="260" ry="135" stroke="currentColor" strokeDasharray="4 4" strokeWidth="1"></ellipse>
                  <circle className="text-secondary/20" cx="400" cy="260" r="190" stroke="currentColor" strokeDasharray="2 4" strokeWidth="0.8"></circle>
                </svg>

                <div className="relative z-20 flex flex-col items-center justify-center transition-transform duration-700 hover:scale-[1.03] pointer-events-none">
                  <img
                    alt="Insightful Games"
                    className="w-[310px] sm:w-[390px] md:w-[480px] max-w-full h-auto object-contain filter drop-shadow-[0_12px_28px_rgba(165,54,5,0.12)] pointer-events-auto"
                    src="https://lh3.googleusercontent.com/aida-public/AB6AXuC5cvnzUVCsIV5Y9kK200mfZ5t6fi3ewr4yEeIF3NtiwPjOGifuWMGPzThVr0d2FIo3BkkiPz8u-gDL7xhRw8Bat33rEaL0ZHQ4M57zWSAJD5spblm7MH7b1feIKwPNOAYoJN1XWnjOVqBvkYb7mzaTKxc_31Gx5bntJwv7cc1VO-WXObKhWKz7KluRC4cNrMSGyD_pIMh5QEsMLZ9ZG_7hAoezhYORpVsHz8RTG_gVOTmH3QUTTgNsfGIAELq31GgLpT8"
                  />
                </div>

                {/* PIEZA 1: REY AJEDREZ */}
                <div
                  className="orbit-track orbit-track-king absolute top-1/2 left-1/2 cursor-pointer focus:outline-none"
                  onClick={() => openBoardModal('chess')}
                  role="button"
                  tabIndex={0}
                  title="Tablero de Ajedrez"
                >
                  <div className="relative flex flex-col items-center group transition-transform duration-300 hover:scale-110">
                    <div className="absolute -bottom-3 w-28 h-6 bg-[#4a1501]/25 rounded-full blur-md pointer-events-none transition-all group-hover:scale-110 group-hover:opacity-40"></div>
                    <div className="relative w-32 h-44 sm:w-36 sm:h-48 md:w-40 md:h-52 flex items-center justify-center filter drop-shadow-[0_22px_32px_rgba(65,22,6,0.38)] group-hover:drop-shadow-[0_26px_42px_rgba(165,54,5,0.58)] transition-all duration-300">
                      <svg className="w-full h-full" fill="none" viewBox="0 0 120 160" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                          <radialGradient cx="38%" cy="28%" id="kingWoodGrad" r="75%">
                            <stop offset="0%" stopColor="#ffc2a6"></stop>
                            <stop offset="28%" stopColor="#cf5622"></stop>
                            <stop offset="65%" stopColor="#882a02"></stop>
                            <stop offset="92%" stopColor="#4e1400"></stop>
                            <stop offset="100%" stopColor="#2a0900"></stop>
                          </radialGradient>
                          <linearGradient id="kingBevelLight" x1="0" x2="1" y1="0" y2="0">
                            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.75"></stop>
                            <stop offset="35%" stopColor="#ffffff" stopOpacity="0.15"></stop>
                            <stop offset="70%" stopColor="#000000" stopOpacity="0.0"></stop>
                            <stop offset="100%" stopColor="#1f0700" stopOpacity="0.7"></stop>
                          </linearGradient>
                          <linearGradient id="goldCrownLight" x1="0" x2="1" y1="0" y2="1">
                            <stop offset="0%" stopColor="#ffe6a3"></stop>
                            <stop offset="50%" stopColor="#d99b26"></stop>
                            <stop offset="100%" stopColor="#694000"></stop>
                          </linearGradient>
                          <filter height="130%" id="kingDepthShadow" width="130%" x="-15%" y="-15%">
                            <feDropShadow dx="3" dy="5" floodColor="#300d02" floodOpacity="0.55" stdDeviation="3.5"></feDropShadow>
                          </filter>
                        </defs>
                        <g filter="url(#kingDepthShadow)">
                          <ellipse cx="60" cy="151" fill="#380d00" opacity="0.7" rx="46" ry="7"></ellipse>
                          <path d="M16 148 C16 141, 104 141, 104 148 C104 155, 16 155, 16 148 Z" fill="url(#kingWoodGrad)"></path>
                          <ellipse cx="60" cy="144" fill="#cf5622" rx="42" ry="4.5"></ellipse>
                          <path d="M22 143 C22 136, 98 136, 98 143 C98 147, 22 147, 22 143 Z" fill="url(#kingWoodGrad)"></path>
                          <path d="M22 143 C35 137, 85 137, 98 143" fill="none" opacity="0.6" stroke="#fff" strokeWidth="1.2"></path>
                          <path d="M26 140 C28 130, 40 123, 44 116 L76 116 C80 123, 92 130, 94 140 Z" fill="url(#kingWoodGrad)"></path>
                          <ellipse cx="60" cy="116" fill="url(#goldCrownLight)" rx="18" ry="4"></ellipse>
                          <ellipse cx="60" cy="115" fill="#ffd885" opacity="0.7" rx="16" ry="2.5"></ellipse>
                          <path d="M44 115 C41 96, 46 80, 43 66 L77 66 C74 80, 79 96, 76 115 Z" fill="url(#kingWoodGrad)"></path>
                          <path d="M46 113 C44 96, 49 80, 46 68 C49 68, 52 95, 50 113 Z" fill="#ffffff" opacity="0.25"></path>
                          <path d="M72 113 C75 96, 71 80, 74 68 C76 72, 76 98, 73 113 Z" fill="#200600" opacity="0.5"></path>
                          <ellipse cx="60" cy="66" fill="url(#goldCrownLight)" rx="19" ry="4.2"></ellipse>
                          <ellipse cx="60" cy="65" fill="#ffe199" opacity="0.8" rx="17" ry="2.5"></ellipse>
                          <path d="M41 65 C39 52, 45 42, 42 34 L78 34 C75 42, 81 52, 79 65 Z" fill="url(#kingWoodGrad)"></path>
                          <ellipse cx="60" cy="34" fill="url(#goldCrownLight)" rx="20" ry="4.5"></ellipse>
                          <path d="M40 34 C36 24, 40 18, 48 16 L72 16 C80 18, 84 24, 80 34 Z" fill="url(#kingWoodGrad)"></path>
                          <path d="M42 30 C40 20, 48 17, 52 24 C54 18, 66 18, 68 24 C72 17, 80 20, 78 30 Z" fill="#b03e0e" opacity="0.85"></path>
                          <ellipse cx="60" cy="16" fill="url(#goldCrownLight)" rx="7" ry="4.5"></ellipse>
                          <circle cx="60" cy="14" fill="url(#goldCrownLight)" r="4.5"></circle>
                          <path d="M57.5 4 L62.5 4 L62.5 13 L57.5 13 Z" fill="url(#goldCrownLight)"></path>
                          <path d="M53.5 6.5 L66.5 6.5 L66.5 10.5 L53.5 10.5 Z" fill="url(#goldCrownLight)"></path>
                          <path d="M58 4.5 L60 4.5 L60 12.5 L58 12.5 Z" fill="#fff" opacity="0.75"></path>
                          <circle cx="60" cy="8.5" fill="#ffffff" opacity="0.9" r="1.2"></circle>
                          <path d="M18 147 C28 142, 38 125, 43 116 L44 66 L42 34 L48 16 L52 16 L48 34 L50 66 L49 116 C45 125, 34 142, 24 148 Z" fill="url(#kingBevelLight)" opacity="0.4"></path>
                        </g>
                      </svg>
                    </div>
                  </div>
                </div>

                {/* PIEZA 2: PIEDRA GO */}
                <div
                  className="orbit-track orbit-track-go absolute top-1/2 left-1/2 cursor-pointer focus:outline-none"
                  onClick={() => openBoardModal('go')}
                  role="button"
                  tabIndex={0}
                  title="Tablero de Go"
                >
                  <div className="relative flex flex-col items-center group transition-transform duration-300 hover:scale-110">
                    <div className="absolute -bottom-4 w-32 h-7 bg-[#1c1613]/35 rounded-full blur-md pointer-events-none transition-all group-hover:scale-110 group-hover:opacity-50"></div>
                    <div className="relative w-32 h-32 sm:w-36 sm:h-36 md:w-40 md:h-40 flex items-center justify-center filter drop-shadow-[0_24px_34px_rgba(20,14,11,0.48)] group-hover:drop-shadow-[0_28px_44px_rgba(123,84,20,0.6)] transition-all duration-300">
                      <div className="relative rounded-full p-[2.5px] bg-gradient-to-br from-stone-400/50 via-stone-800 to-black shadow-inner flex items-center justify-center w-full h-full">
                        <div className="w-full h-full rounded-full relative overflow-hidden bg-[radial-gradient(ellipse_at_34%_26%,_#5a534d_0%,_#25201d_42%,_#0e0c0b_82%,_#020101_100%)] shadow-[inset_0_5px_16px_rgba(255,255,255,0.3),inset_0_-10px_20px_rgba(0,0,0,0.9)]">
                          <div className="absolute top-3.5 left-5 w-14 h-7 rounded-full bg-gradient-to-b from-white/75 via-white/25 to-transparent rotate-[-24deg] blur-[0.8px]"></div>
                          <div className="absolute bottom-3.5 right-4 w-12 h-6 rounded-full bg-emerald-500/25 blur-[4px]"></div>
                          <div className="absolute inset-0 rounded-full border border-black/60 pointer-events-none"></div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* PIEZA 3: KOMA SHOGI */}
                <div
                  className="orbit-track orbit-track-shogi absolute top-1/2 left-1/2 cursor-pointer focus:outline-none"
                  onClick={() => openBoardModal('shogi')}
                  role="button"
                  tabIndex={0}
                  title="Tablero de Shogi"
                >
                  <div className="relative flex flex-col items-center group transition-transform duration-300 hover:scale-110">
                    <div className="absolute -bottom-4 w-32 h-7 bg-[#543b1c]/35 rounded-full blur-md pointer-events-none transition-all group-hover:scale-110 group-hover:opacity-50"></div>
                    <div className="relative w-32 h-40 sm:w-36 sm:h-44 md:w-40 md:h-48 flex items-center justify-center filter drop-shadow-[0_24px_32px_rgba(55,36,14,0.42)] group-hover:drop-shadow-[0_28px_44px_rgba(85,98,74,0.6)] transition-all duration-300">
                      <svg className="w-full h-full" fill="none" viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                          <linearGradient id="shogiFrontLg" x1="0.3" x2="0.7" y1="0" y2="1">
                            <stop offset="0%" stopColor="#faebd2"></stop>
                            <stop offset="45%" stopColor="#edd5b3"></stop>
                            <stop offset="100%" stopColor="#d6b88b"></stop>
                          </linearGradient>
                          <linearGradient id="shogiSideLg" x1="0" x2="1" y1="0" y2="0">
                            <stop offset="0%" stopColor="#b89360"></stop>
                            <stop offset="100%" stopColor="#7e5d32"></stop>
                          </linearGradient>
                          <linearGradient id="shogiBottomLg" x1="0" x2="0" y1="0" y2="1">
                            <stop offset="0%" stopColor="#8a6838"></stop>
                            <stop offset="100%" stopColor="#543c1c"></stop>
                          </linearGradient>
                          <linearGradient id="shogiBevelLg" x1="0" x2="0" y1="0" y2="1">
                            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.85"></stop>
                            <stop offset="100%" stopColor="#ffffff" stopOpacity="0.0"></stop>
                          </linearGradient>
                        </defs>
                        <path d="M50 8 L87 27 L95 32 L58 13 Z" fill="url(#shogiSideLg)" opacity="0.85"></path>
                        <path d="M87 27 L78 102 L86 106 L95 32 Z" fill="url(#shogiSideLg)"></path>
                        <path d="M22 102 L78 102 L86 106 L28 106 Z" fill="url(#shogiBottomLg)"></path>
                        <path d="M50 8 L87 27 L78 102 L22 102 L13 27 Z" fill="url(#shogiFrontLg)" stroke="#ecd0a8" strokeWidth="0.85"></path>
                        <path d="M50 9 L86 28 L84 31 L50 12 L16 31 L14 28 Z" fill="url(#shogiBevelLg)"></path>
                        <path d="M24 35 Q45 42 76 33" fill="none" opacity="0.6" stroke="#d4b488" strokeWidth="0.9"></path>
                        <path d="M22 62 Q50 68 78 58" fill="none" opacity="0.5" stroke="#d4b488" strokeWidth="0.9"></path>
                        <path d="M23 88 Q48 94 77 85" fill="none" opacity="0.6" stroke="#d4b488" strokeWidth="0.9"></path>
                        <g fill="#1a1107">
                          <path d="M34 38 h32 v3.5 h-13.5 v9 h12 v3.5 h-12 v9.5 h14.5 v4 h-34 v-4 h14 v-9.5 h-11.5 v-3.5 h11.5 v-9 h-13 v-3.5 z" fill="#1b1512"></path>
                          <path d="M32 73 h7 v18 h-7 z M36 78 h13 v3.5 h-13 z M43 73 h6 v21 h-6 z M53 72 h15 v3 h-15 z M52 79 h17 v3 h-17 z M51 86 h19 v3.2 h-19 z M61 69 h4.5 v25 h-4.5 z" fill="#1b1512"></path>
                        </g>
                      </svg>
                    </div>
                  </div>
                </div>
              </div>

              {/* HERO TEXT */}
              <div className="max-w-3xl text-center flex flex-col items-center">
                <div className="inline-flex items-center gap-space-xs px-space-sm py-1 rounded-full bg-surface-container text-tertiary mb-space-md shadow-sm">
                  <span className="material-symbols-outlined text-sm">psychology_alt</span>
                  <span className="font-label-sm text-label-sm uppercase tracking-wider">Metodología de Pensamiento Pausado</span>
                </div>
                <h1 className="font-headline-xl text-headline-xl text-on-surface tracking-tight mb-space-sm">
                  Aprende juegos de estrategia, diviértete y mejora tu pensamiento estratégico.
                </h1>
                <p className="font-body-lg text-body-lg text-on-surface-variant max-w-2xl mb-space-lg leading-relaxed">
                  Ajedrez, Go y Shogi guiados por un <span className="text-primary font-semibold">Tutor con Inteligencia Artificial</span> que se adapta a tu forma de razonar, sin abrumarte y yendo a tu ritmo.
                </p>

                <div className="flex flex-col sm:flex-row items-center gap-space-md w-full sm:w-auto">
                  <button
                    onClick={onLogin}
                    className="w-full sm:w-auto px-space-lg py-space-sm rounded-xl bg-primary text-on-primary font-label-lg text-label-lg shadow-md hover:bg-primary-container hover:shadow-lg transition-all duration-300 flex items-center justify-center gap-space-xs cursor-pointer"
                  >
                    <span>Comenzar gratis — Registrarme</span>
                    <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
                  </button>
                  <a
                    href="#juegos-milenarios"
                    className="w-full sm:w-auto px-space-lg py-space-sm rounded-xl bg-surface-container-high text-on-surface font-label-lg text-label-lg hover:bg-surface-container-highest transition-colors flex items-center justify-center gap-space-xs shadow-sm"
                  >
                    <span className="material-symbols-outlined text-[18px]">explore</span>
                    <span>Explorar los 3 Juegos</span>
                  </a>
                </div>

                <div className="mt-space-lg flex flex-wrap items-center justify-center gap-x-space-lg gap-y-space-xs text-on-surface-variant font-label-md text-label-md">
                  <div className="flex items-center gap-space-xs">
                    <span className="material-symbols-outlined text-primary text-[18px]">check_circle</span>
                    <span>Modo Un Jugador contra IA pedagógica</span>
                  </div>
                  <div className="flex items-center gap-space-xs">
                    <span className="material-symbols-outlined text-secondary text-[18px]">check_circle</span>
                    <span>Multijugador amistoso en línea</span>
                  </div>
                  <div className="flex items-center gap-space-xs">
                    <span className="material-symbols-outlined text-tertiary text-[18px]">check_circle</span>
                    <span>100% libre de puzzles rutinarios</span>
                  </div>
                </div>
              </div>

            </div>
          </section>

          {/* FILOSOFÍA */}
          <section className="w-full bg-surface-container-lowest py-space-xl px-gutter md:px-margin" id="filosofia">
            <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center gap-space-xl">
              <div className="w-full md:w-1/2 flex flex-col gap-space-md">
                <span className="font-label-sm text-label-sm uppercase tracking-widest text-primary font-bold">Concepto &amp; Manifiesto</span>
                <h2 className="font-headline-lg text-headline-lg text-on-surface">
                  Un espacio donde cada movimiento cuenta una historia humana.
                </h2>
                <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">
                  Los motores modernos calculan millones de variantes por segundo pero no saben explicarte el por qué de una decisión en palabras sencillas. Insightful Games te da retroalimentación, explicación y heurísticas de cada jugada y estrategia, para que desarrolles tu intuición.
                </p>
                <div className="grid grid-cols-2 gap-space-md pt-space-xs">
                  <div className="p-space-md rounded-xl bg-surface-container-low shadow-sm">
                    <span className="font-headline-sm text-headline-sm text-primary block mb-1">01</span>
                    <h4 className="font-label-lg text-label-lg text-on-surface mb-1 font-semibold">Conversación viva</h4>
                    <p className="font-body-sm text-body-sm text-on-surface-variant">Pregunta dudas en tiempo real durante tu partida y recibe respuestas comprensibles.</p>
                  </div>
                  <div className="p-space-md rounded-xl bg-surface-container-low shadow-sm">
                    <span className="font-headline-sm text-headline-sm text-secondary block mb-1">02</span>
                    <h4 className="font-label-lg text-label-lg text-on-surface mb-1 font-semibold">Sin castigos</h4>
                    <p className="font-body-sm text-body-sm text-on-surface-variant">Sin racha obligatoria ni ejercicios forzados. Juega y aprende a tu propio ritmo.</p>
                  </div>
                </div>
              </div>

              <div className="w-full md:w-1/2 relative flex items-center justify-center">
                <div className="w-full max-w-md p-space-lg rounded-3xl bg-gradient-to-tr from-surface-container-high/60 to-surface-container-low border border-outline-variant/40 shadow-xl flex flex-col items-center text-center">
                  <div className="w-20 h-20 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-space-md">
                    <span className="material-symbols-outlined text-[44px]">menu_book</span>
                  </div>
                  <h3 className="font-headline-sm text-headline-sm text-on-surface mb-space-xs">Intuición antes que memoria ciega</h3>
                  <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed">
                    En lugar de memorizar 30 jugadas de apertura sin comprenderlas, comprende el equilibrio de masas, las diagonales y el flujo territorial que une a los tres grandes juegos.
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* JUEGOS MILENARIOS */}
          <section className="w-full bg-surface py-space-xl px-gutter md:px-margin" id="juegos-milenarios">
            <div className="max-w-6xl mx-auto flex flex-col gap-space-xl">
              <div className="flex flex-col md:flex-row md:items-end justify-between gap-space-md">
                <div className="max-w-2xl">
                  <h2 className="font-headline-lg text-headline-lg text-on-surface mt-1">
                    Tres universos. Una sola mente expandida.
                  </h2>
                  <p className="font-body-md text-body-md text-on-surface-variant mt-space-xs">
                    Domina las tres disciplinas canónicas del pensamiento en juegos estratégicos milenarios. Juega contra Bots pedagógicos adaptativos o desafía a amigos en modo multijugador.
                  </p>
                </div>
                <div className="inline-flex items-center gap-space-xs px-space-md py-space-xs rounded-xl bg-surface-container-high text-on-surface font-label-md text-label-md shadow-sm">
                  <span className="material-symbols-outlined text-primary text-[18px]">sports_esports</span>
                  <span>Modos: 1P vs Tutor IA • Multijugador</span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-space-lg">
                {/* AJEDREZ CARD */}
                <div className="flex flex-col rounded-2xl bg-surface-container-low p-space-lg shadow-md hover:shadow-xl transition-all duration-300 relative group overflow-hidden">
                  <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-space-md group-hover:scale-110 transition-transform">
                    <span className="material-symbols-outlined text-[28px]">token</span>
                  </div>
                  <span className="font-label-sm text-label-sm text-primary font-bold uppercase tracking-wider">Occidente &amp; Perspicacia</span>
                  <h3 className="font-headline-md text-headline-md text-on-surface mt-1 mb-space-xs">Ajedrez Clásico</h3>
                  <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed mb-space-md">
                    Dominio posicional, sincronía de piezas mayores y cálculo de rupturas. El Tutor te explica los temas geométricos (clavadas, rayos X, peones aislados) con lenguaje natural.
                  </p>
                  <div className="mt-auto pt-space-md border-t border-outline-variant/30 flex flex-col gap-space-xs">
                    <button
                      className="mt-space-sm w-full py-space-xs rounded-lg bg-surface-container-highest text-on-surface font-label-md text-label-md hover:bg-primary hover:text-on-primary transition-colors flex items-center justify-center gap-1 shadow-sm cursor-pointer"
                      onClick={() => openBoardModal('chess')}
                    >
                      <span>Abrir Tablero de Ajedrez</span>
                      <span className="material-symbols-outlined text-[16px]">chevron_right</span>
                    </button>
                  </div>
                </div>

                {/* GO CARD */}
                <div className="flex flex-col rounded-2xl bg-surface-container-low p-space-lg shadow-md hover:shadow-xl transition-all duration-300 relative group overflow-hidden">
                  <div className="w-12 h-12 rounded-xl bg-tertiary/10 text-tertiary flex items-center justify-center mb-space-md group-hover:scale-110 transition-transform">
                    <span className="material-symbols-outlined text-[28px]">radio_button_checked</span>
                  </div>
                  <span className="font-label-sm text-label-sm text-tertiary font-bold uppercase tracking-wider">Oriente &amp; Infinitud</span>
                  <h3 className="font-headline-md text-headline-md text-on-surface mt-1 mb-space-xs">Go (Weiqi / Baduk)</h3>
                  <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed mb-space-md">
                    La belleza de construir territorio con piedras iguales sobre una cuadrícula de 19x19, 13x13 o 9x9. Comprende 'vida y muerte', ojos y formas orgánicas sin tecnicismos incomprensibles.
                  </p>
                  <div className="mt-auto pt-space-md border-t border-outline-variant/30 flex flex-col gap-space-xs">
                    <button
                      className="mt-space-sm w-full py-space-xs rounded-lg bg-surface-container-highest text-on-surface font-label-md text-label-md hover:bg-tertiary hover:text-on-tertiary transition-colors flex items-center justify-center gap-1 shadow-sm cursor-pointer"
                      onClick={() => openBoardModal('go')}
                    >
                      <span>Abrir Tablero de Go</span>
                      <span className="material-symbols-outlined text-[16px]">chevron_right</span>
                    </button>
                  </div>
                </div>

                {/* SHOGI CARD */}
                <div className="flex flex-col rounded-2xl bg-surface-container-low p-space-lg shadow-md hover:shadow-xl transition-all duration-300 relative group overflow-hidden">
                  <div className="w-12 h-12 rounded-xl bg-secondary/10 text-secondary flex items-center justify-center mb-space-md group-hover:scale-110 transition-transform">
                    <span className="material-symbols-outlined text-[28px]">change_circle</span>
                  </div>
                  <span className="font-label-sm text-label-sm text-secondary font-bold uppercase tracking-wider">Japón &amp; Resurrección</span>
                  <h3 className="font-headline-md text-headline-md text-on-surface mt-1 mb-space-xs">Shogi</h3>
                  <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed mb-space-md">
                    El ajedrez japonés donde cada pieza enemiga capturada puede ser devuelta al tablero a tu favor. Partidas dinámicas sin tablas forzadas y ascensos de rango tras penetrar líneas enemigas.
                  </p>
                  <div className="mt-auto pt-space-md border-t border-outline-variant/30 flex flex-col gap-space-xs">
                    <button
                      className="mt-space-sm w-full py-space-xs rounded-lg bg-surface-container-highest text-on-surface font-label-md text-label-md hover:bg-secondary hover:text-on-secondary transition-colors flex items-center justify-center gap-1 shadow-sm cursor-pointer"
                      onClick={() => openBoardModal('shogi')}
                    >
                      <span>Abrir Tablero de Shogi</span>
                      <span className="material-symbols-outlined text-[16px]">chevron_right</span>
                    </button>
                  </div>
                </div>
              </div>

            </div>
          </section>

          {/* CTA FINAL */}
          <section className="w-full bg-gradient-to-tr from-surface via-surface-container to-surface-container-high py-space-xl px-gutter md:px-margin">
            <div className="max-w-4xl mx-auto rounded-3xl bg-surface p-space-lg md:p-space-xl shadow-xl flex flex-col md:flex-row items-center justify-between gap-space-lg relative overflow-hidden">
              <div className="flex flex-col gap-space-xs max-w-xl text-left">
                <span className="font-label-sm text-label-sm uppercase tracking-widest text-primary font-bold">Unirse a la Hermandad de Jugadores</span>
                <h2 className="font-headline-lg text-headline-lg text-on-surface">
                  Tu próximo movimiento comienza con serenidad.
                </h2>
                <p className="font-body-md text-body-md text-on-surface-variant">
                  Crea tu cuenta gratuita en menos de 30 segundos. Sin datos bancarios, sin publicidad intrusiva, solo tú y el tablero.
                </p>
              </div>
              <div className="w-full md:w-auto flex flex-col sm:flex-row md:flex-col gap-space-sm shrink-0">
                <button
                  onClick={onLogin}
                  className="px-space-xl py-space-sm rounded-xl bg-primary text-on-primary font-label-lg text-label-lg shadow-md hover:bg-primary-container text-center transition-all cursor-pointer"
                >
                  Registrarme Gratis
                </button>
                <button
                  onClick={onLogin}
                  className="px-space-xl py-space-sm rounded-xl bg-surface-container-high text-on-surface font-label-lg text-label-lg hover:bg-surface-container-highest text-center transition-colors cursor-pointer"
                >
                  Ya tengo cuenta
                </button>
              </div>
            </div>
          </section>

        </div>
      </main>

      {/* FOOTER */}
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

      {/* MODAL VISOR INTERACTIVO DE TABLEROS */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/60 backdrop-blur-md overflow-y-auto animate-fadeIn">
          <div className="relative w-full max-w-5xl bg-surface rounded-2xl shadow-2xl border border-outline-variant/40 overflow-hidden flex flex-col max-h-[92vh] my-auto">
            {/* Header Modal */}
            <div className="px-5 py-4 border-b border-outline-variant/30 bg-surface-container-low flex items-center justify-between gap-3 shrink-0">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${boardMetadata[activeBoard].iconClass}`}>
                  <span className="material-symbols-outlined text-[24px]">{boardMetadata[activeBoard].icon}</span>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold">{boardMetadata[activeBoard].title}</h3>
                    <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider ${boardMetadata[activeBoard].badgeClass}`}>{boardMetadata[activeBoard].badge}</span>
                  </div>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">{boardMetadata[activeBoard].subtitle}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="hidden sm:flex bg-surface-container rounded-xl p-1 gap-1 border border-outline-variant/20">
                  <button
                    className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1 cursor-pointer ${activeBoard === 'chess' ? 'bg-surface text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}`}
                    onClick={() => setActiveBoard('chess')}
                  >
                    <span className="material-symbols-outlined text-[14px]">token</span> Ajedrez
                  </button>
                  <button
                    className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1 cursor-pointer ${activeBoard === 'go' ? 'bg-surface text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}`}
                    onClick={() => setActiveBoard('go')}
                  >
                    <span className="material-symbols-outlined text-[14px]">radio_button_checked</span> Go
                  </button>
                  <button
                    className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1 cursor-pointer ${activeBoard === 'shogi' ? 'bg-surface text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}`}
                    onClick={() => setActiveBoard('shogi')}
                  >
                    <span className="material-symbols-outlined text-[14px]">change_circle</span> Shogi
                  </button>
                </div>
                <button
                  aria-label="Cerrar visor"
                  className="w-9 h-9 rounded-full bg-surface-container hover:bg-surface-container-highest text-on-surface flex items-center justify-center transition-colors cursor-pointer"
                  onClick={closeBoardModal}
                >
                  <span className="material-symbols-outlined text-[20px]">close</span>
                </button>
              </div>
            </div>

            {/* Pestañas móviles */}
            <div className="flex sm:hidden bg-surface-container px-3 py-2 border-b border-outline-variant/20 gap-2 shrink-0">
              <button
                className={`flex-1 py-1 text-xs font-semibold rounded-lg text-center ${activeBoard === 'chess' ? 'bg-surface text-primary shadow-sm' : 'text-on-surface-variant'}`}
                onClick={() => setActiveBoard('chess')}
              >
                Ajedrez
              </button>
              <button
                className={`flex-1 py-1 text-xs font-semibold rounded-lg text-center ${activeBoard === 'go' ? 'bg-surface text-primary shadow-sm' : 'text-on-surface-variant'}`}
                onClick={() => setActiveBoard('go')}
              >
                Go
              </button>
              <button
                className={`flex-1 py-1 text-xs font-semibold rounded-lg text-center ${activeBoard === 'shogi' ? 'bg-surface text-primary shadow-sm' : 'text-on-surface-variant'}`}
                onClick={() => setActiveBoard('shogi')}
              >
                Shogi
              </button>
            </div>

            {/* Contenido Modal */}
            <div className="p-4 sm:p-6 overflow-y-auto flex-1 bg-surface-container-lowest">
              {/* Contenido de cada juego omitido para brevedad en esta respuesta; usa el mismo que antes */}
            </div>
            {/* Footer Modal */}
            <div className="px-5 py-3 border-t border-outline-variant/20 bg-surface-container flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-on-surface-variant shrink-0">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[16px]">info</span>
                <span>Pulsa <kbd className="px-1.5 py-0.5 bg-surface-container-highest rounded border border-outline-variant/40 font-mono text-[10px]">ESC</kbd> o haz clic fuera para cerrar.</span>
              </div>
              <button
                className="px-4 py-1.5 rounded-lg bg-surface-container-highest hover:bg-surface-container-high text-on-surface font-semibold transition-colors cursor-pointer"
                onClick={closeBoardModal}
              >
                Cerrar Previsualización
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
