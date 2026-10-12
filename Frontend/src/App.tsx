import { useState } from 'react';
import Landing from './components/Landing';
import Login from './components/Login';

export default function App() {
  const [showLogin, setShowLogin] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<{ userId: string; username: string } | null>(null);

  const handleLoginSuccess = (token: string, userData: { userId: string; username: string }) => {
    localStorage.setItem('accessToken', token);
    localStorage.setItem('user', JSON.stringify(userData));
    setIsAuthenticated(true);
    setUser(userData);
    setShowLogin(false);
  };

  const handleLogout = () => {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('user');
    setIsAuthenticated(false);
    setUser(null);
  };

  // Al cargar, revisar si hay token guardado
  // (se ejecuta en useEffect en Landing para evitar SSR issues)

  if (isAuthenticated) {
    return <Landing onLogin={() => setShowLogin(true)} user={user} onLogout={handleLogout} />;
  }

  return showLogin ? (
    <Login onLoginSuccess={handleLoginSuccess} onBack={() => setShowLogin(false)} />
  ) : (
    <Landing onLogin={() => setShowLogin(true)} />
  );
}