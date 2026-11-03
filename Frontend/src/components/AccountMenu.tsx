import { useEffect, useId, useRef, useState } from 'react';

interface AccountMenuProps {
  /** Nombre a mostrar; null si la sesión es válida pero el perfil aún no está disponible. */
  username: string | null;
  onLogout: () => void;
}

const itemClass =
  'flex items-center gap-space-sm px-space-md py-space-sm font-label-lg text-label-lg text-on-surface hover:bg-surface-container-high focus:bg-surface-container-high focus:outline-none cursor-pointer w-full text-left';

/**
 * Menú de la cuenta en el encabezado (ícono de usuario): Mi perfil, Estadísticas y Cerrar sesión.
 * Se abre con clic o teclado y se cierra con Escape, con clic fuera o al elegir una opción.
 */
export default function AccountMenu({ username, onLogout }: AccountMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    // Al abrir, el foco pasa a la primera opción.
    rootRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative flex items-center gap-space-sm">
      <span className="hidden sm:inline font-label-lg text-label-lg text-on-surface">
        Hola{username ? `, ${username}` : ''}
      </span>
      <button
        ref={buttonRef}
        type="button"
        aria-label="Menú de la cuenta"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-on-primary shadow-sm hover:bg-primary-container focus:outline-none focus:ring-2 focus:ring-primary/40 transition-colors cursor-pointer"
      >
        <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
          person
        </span>
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label="Cuenta"
          className="absolute right-0 top-full mt-space-xs w-56 py-space-xs rounded-xl bg-surface-container-lowest border border-outline-variant/40 shadow-lg z-50"
        >
          <a role="menuitem" href="/perfil" className={itemClass} onClick={() => setOpen(false)}>
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
              account_circle
            </span>
            Mi perfil
          </a>
          <a role="menuitem" href="/estadisticas" className={itemClass} onClick={() => setOpen(false)}>
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
              bar_chart
            </span>
            Estadísticas
          </a>
          <button
            role="menuitem"
            type="button"
            className={`${itemClass} border-t border-outline-variant/30 text-error`}
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
              logout
            </span>
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  );
}
