import { useState, useEffect } from 'react';
import Landing from './components/Landing';
import Login from './components/Login';
import Dashboard from './components/Dashboard';

export default function App() {
  const [showLogin, setShowLogin] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<{ userId: string; username: string } | null>(null);
  const [token, setToken] = useState<string | null>(null);

  const handleLoginSuccess = (token: string, userData: { userId: string; username: string }) => {
    localStorage.setItem('accessToken', token);
    localStorage.setItem('user', JSON.stringify(userData));
    setToken(token);
    setIsAuthenticated(true);
    setUser(userData);
    setShowLogin(false);
  };

  const handleLogout = () => {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('user');
    setToken(null);
    setIsAuthenticated(false);
    setUser(null);
  };

  // Al cargar, revisar si hay token guardado
  useEffect(() => {
    const savedToken = localStorage.getItem('accessToken');
    const savedUser = localStorage.getItem('user');
    if (savedToken && savedUser) {
      try {
        const userData = JSON.parse(savedUser);
        setToken(savedToken);
        setIsAuthenticated(true);
        setUser(userData);
      } catch {
        // Token inválido, limpiar
        localStorage.removeItem('accessToken');
        localStorage.removeItem('user');
      }
    }
  }, []);

  if (isAuthenticated && token && user) {
    return <Dashboard user={user} token={token} onLogout={handleLogout} />;
  }

  return showLogin ? (
    <Login onLoginSuccess={handleLoginSuccess} onBack={() => setShowLogin(false)} />
  ) : (
    <Landing onLogin={() => setShowLogin(true)} />
  );
}