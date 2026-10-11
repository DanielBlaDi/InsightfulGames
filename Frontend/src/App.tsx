import { useState } from 'react';
import Landing from './components/Landing';
import Login from './components/Login';

export default function App() {
  const [showLogin, setShowLogin] = useState(false);
  return showLogin ? <Login /> : <Landing onLogin={() => setShowLogin(true)} />;
}
