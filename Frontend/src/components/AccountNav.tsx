import { useState } from 'react';
import { logout } from '../auth/session';

interface AccountNavProps {
  /** Página actual, para marcarla en la barra. */
  current?: 'perfil' | 'estadisticas';
}

const linkClass = (active: boolean) =>
  `inline-flex items-center gap-space-xs px-space-sm py-space-xs rounded-lg font-label-lg text-label-lg transition-colors ${
    active ? 'bg-primary/10 text-primary' : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high'
  }`;

/**
 * Barra de las páginas de la cuenta (/perfil y /estadisticas): Inicio, Mi perfil, Estadísticas y
 * Cerrar sesión. Apta para renderizarse en el servidor: no toca window al renderizar.
 */
export default function AccountNav({ current }: AccountNavProps) {
  const [leaving, setLeaving] = useState(false);
  const [logoutFailed, setLogoutFailed] = useState(false);

  const handleLogout = async () => {
    setLeaving(true);
    setLogoutFailed(false);
    if (await logout()) {
      window.location.assign('/');
    } else {
      setLeaving(false);
      setLogoutFailed(true);
    }
  };

  return (
    <header className="w-full bg-surface/90 backdrop-blur-md shadow-[0_1px_8px_rgba(76,56,36,0.05)]">
      <nav
        aria-label="Cuenta"
        className="max-w-3xl mx-auto px-gutter-mobile md:px-0 py-space-sm flex flex-wrap items-center justify-between gap-space-sm"
      >
        <a href="/" className={linkClass(false)}>
          <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
            home
          </span>
          Inicio
        </a>
        <div className="flex flex-wrap items-center gap-space-xs">
          <a href="/perfil" className={linkClass(current === 'perfil')} aria-current={current === 'perfil' ? 'page' : undefined}>
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
              account_circle
            </span>
            Mi perfil
          </a>
          <a
            href="/estadisticas"
            className={linkClass(current === 'estadisticas')}
            aria-current={current === 'estadisticas' ? 'page' : undefined}
          >
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
              bar_chart
            </span>
            Estadísticas
          </a>
          <button
            type="button"
            onClick={handleLogout}
            disabled={leaving}
            className="inline-flex items-center gap-space-xs px-space-sm py-space-xs rounded-lg font-label-lg text-label-lg bg-surface-container-high text-on-surface hover:bg-error-container transition-colors cursor-pointer disabled:opacity-60"
          >
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
              logout
            </span>
            {leaving ? 'Saliendo…' : 'Cerrar sesión'}
          </button>
        </div>
      </nav>
      {logoutFailed && (
        <p role="alert" className="max-w-3xl mx-auto px-gutter-mobile md:px-0 pb-space-sm font-body-sm text-body-sm text-error">
          No se pudo cerrar la sesión. Inténtalo de nuevo.
        </p>
      )}
    </header>
  );
}
