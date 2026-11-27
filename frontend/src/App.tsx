import { useEffect, useState } from 'react';
import { clearLegacyStorage, logout, readSession } from './auth/session';
import type { SessionState, SessionUser } from './auth/session';
import Landing from './components/Landing';
import Login from './components/Login';
import { PlayChess } from './game';

type View = 'landing' | 'login' | 'chess';

export default function App() {
  const [session, setSession] = useState<SessionState>({ status: 'checking' });
  const [view, setView] = useState<View>('landing');
  // El usuario pidió jugar ajedrez sin sesión: tras el login se le lleva directo a la partida.
  const [chessAfterLogin, setChessAfterLogin] = useState(false);

  const show = (next: View) => {
    setView(next);
    window.scrollTo(0, 0);
  };

  // Al cargar (y al reintentar): la sonda GET /api/stats/me dice si hay sesión (5.4.4). El nombre
  // sale de GET /api/profile/me; si ese falla con 404 o 503, la sesión sigue siendo válida.
  const [sessionCheck, setSessionCheck] = useState(0);

  useEffect(() => {
    let active = true;
    clearLegacyStorage();
    void readSession().then((next) => {
      if (active) setSession(next);
    });
    return () => {
      active = false;
    };
  }, [sessionCheck]);

  const retrySession = () => {
    setSession({ status: 'checking' });
    setSessionCheck((n) => n + 1);
  };

  const handleLoginSuccess = (user: SessionUser) => {
    // La cookie ya llegó con la respuesta del login; solo se actualiza el encabezado.
    setSession({ status: 'authenticated', username: user.username });
    show(chessAfterLogin ? 'chess' : 'landing');
    setChessAfterLogin(false);
  };

  const handleLogout = async () => {
    if (!(await logout())) {
      window.alert('No se pudo cerrar la sesión. Inténtalo de nuevo.');
      return;
    }
    setSession({ status: 'anonymous' });
    setChessAfterLogin(false);
    show('landing');
  };

  const handlePlayChess = () => {
    if (session.status === 'authenticated') {
      show('chess');
    } else {
      setChessAfterLogin(true);
      show('login');
    }
  };

  // El Gateway rechazó la sesión (401 en REST o cierre 4401 del WebSocket): se pide iniciar sesión
  // de nuevo y se vuelve al ajedrez al terminar.
  const handleUnauthorized = () => {
    setSession({ status: 'anonymous' });
    setChessAfterLogin(true);
    show('login');
  };

  if (view === 'chess' && session.status === 'authenticated') {
    return <PlayChess onUnauthorized={handleUnauthorized} onExit={() => show('landing')} />;
  }

  if (view === 'login' && session.status !== 'authenticated') {
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
        if (session.status !== 'authenticated') show('login');
      }}
      onPlayChess={handlePlayChess}
      session={session}
      onRetrySession={retrySession}
      onLogout={handleLogout}
    />
  );
}
