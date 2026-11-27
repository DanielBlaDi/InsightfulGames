import { safeNext } from '../../src/auth/session';
import Login from '../../src/components/Login';

// Ruta /login provisional: destino del 302 de /estadisticas (5.4.3) y del 401 de /perfil.
// Reutiliza Login.tsx. El gateway ya dejó la cookie session al responder al login, así que aquí no
// se guarda el token: se navega con recarga completa para que el servidor vea la cookie.
// Frontend A la sustituye por su página de login definitiva.
export default function Page() {
  return (
    <Login
      onLoginSuccess={() => window.location.assign(safeNext(window.location.search, window.location.origin))}
      onBack={() => window.location.assign('/')}
    />
  );
}
