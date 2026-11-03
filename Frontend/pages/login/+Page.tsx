import Login from '../../src/components/Login';

/**
 * Solo rutas del propio sitio (evita redirecciones abiertas con next=https://otro.sitio o //otro).
 * Sin next válido se vuelve al inicio.
 */
function safeNext(): string {
  const next = new URLSearchParams(window.location.search).get('next');
  if (!next) return '/';
  const target = new URL(next, window.location.origin);
  return target.origin === window.location.origin ? target.pathname + target.search + target.hash : '/';
}

// Ruta /login provisional: destino del 302 de /estadisticas (5.4.3). Reutiliza Login.tsx sin
// cambios. El gateway ya dejó la cookie session al responder al login, así que aquí no se guarda
// el token: se navega con recarga completa para que el servidor vea la cookie.
// Frontend A la sustituye por su página de login definitiva.
export default function Page() {
  return (
    <Login
      onLoginSuccess={() => window.location.assign(safeNext())}
      onBack={() => window.location.assign('/')}
    />
  );
}
