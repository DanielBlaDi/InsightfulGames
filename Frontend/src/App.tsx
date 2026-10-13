import { useState } from 'react';
import { clearSession, loadSession, saveSession } from './authSession';
import type { AuthSession, AuthUser } from './authSession';
import Landing from './components/Landing';
import Login from './components/Login';
import { PlayChess } from './game';

type View = 'landing' | 'login' | 'chess';

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(loadSession);
  const [view, setView] = useState<View>('landing');
  // El usuario pidió jugar ajedrez sin sesión: tras el login se le lleva directo a la partida.
  const [chessAfterLogin, setChessAfterLogin] = useState(false);

  const show = (next: View) => {
    setView(next);
    window.scrollTo(0, 0);
  };

  const handleLoginSuccess = (token: string, user: AuthUser) => {
    const next = { token, user };
    saveSession(next);
    setSession(next);
    show(chessAfterLogin ? 'chess' : 'landing');
    setChessAfterLogin(false);
  };

  const handleLogout = () => {
    clearSession();
    setSession(null);
    setChessAfterLogin(false);
    show('landing');
  };

  const handlePlayChess = () => {
    if (session) {
      show('chess');
    } else {
      setChessAfterLogin(true);
      show('login');
    }
  };

  // El Gateway rechazó el token (401 en REST o cierre 4401 del WebSocket): la sesión ya no
  // sirve. Se pide iniciar sesión de nuevo y se vuelve al ajedrez al terminar.
  const handleUnauthorized = () => {
    clearSession();
    setSession(null);
    setChessAfterLogin(true);
    show('login');
  };

  if (view === 'chess' && session) {
    return <PlayChess token={session.token} onUnauthorized={handleUnauthorized} onExit={() => show('landing')} />;
  }

  if (view === 'login' && !session) {
    return (
      <Login
        onLoginSuccess={handleLoginSuccess}
        onBack={() => {
          setChessAfterLogin(false);
          show('landing');
        }}
      />
    );
  }

  return (
    <Landing
      onLogin={() => {
        if (!session) show('login');
      }}
      onPlayChess={handlePlayChess}
      user={session?.user}
      onLogout={handleLogout}
    />
  );
}
