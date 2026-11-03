import { useEffect, useState } from 'react';
import { fetchProfile, loginUrl } from '../auth/session';
import type { Profile } from '../auth/session';
import AccountNav from '../components/AccountNav';

export const PROFILE_PATH = '/perfil';

type ProfileState =
  | { kind: 'loading' }
  | { kind: 'ok'; profile: Profile }
  | { kind: 'not_found' }
  | { kind: 'unavailable' }
  | { kind: 'redirecting' };

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('es', { dateStyle: 'long' }).format(date);
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-1 py-space-sm border-b border-outline-variant/30 last:border-b-0">
      <dt className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant">{label}</dt>
      <dd className={`text-on-surface break-all ${mono ? 'font-mono text-body-sm' : 'font-body-lg text-body-lg'}`}>{value}</dd>
    </div>
  );
}

function Notice({ icon, title, text, onRetry }: { icon: string; title: string; text: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="p-space-lg rounded-2xl bg-surface-container-low border border-outline-variant/30 text-center flex flex-col items-center gap-space-sm"
    >
      <span className="material-symbols-outlined text-[40px] text-on-surface-variant" aria-hidden="true">
        {icon}
      </span>
      <p className="font-headline-sm text-headline-sm text-on-surface">{title}</p>
      <p className="font-body-md text-body-md text-on-surface-variant">{text}</p>
      <button
        type="button"
        onClick={onRetry}
        className="px-space-md py-space-xs rounded-lg bg-primary text-on-primary font-label-lg text-label-lg shadow-sm hover:bg-primary-container transition-colors cursor-pointer"
      >
        Reintentar
      </button>
    </div>
  );
}

/**
 * /perfil: aplicación de una sola página (ssr: false). Pide GET /api/profile/me con la cookie de
 * sesión. 401 → login con next=/perfil; 404 → la sesión es válida pero el perfil aún no existe
 * (nace con user.registered, de forma asíncrona); 503 u otros → aviso con reintento.
 */
export default function ProfilePage() {
  const [state, setState] = useState<ProfileState>({ kind: 'loading' });

  // Cada reintento sube `attempt` y vuelve a pedir el perfil.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    void fetchProfile().then((result) => {
      if (!active) return;
      if (result.kind === 'unauthenticated') {
        setState({ kind: 'redirecting' });
        window.location.replace(loginUrl(PROFILE_PATH));
      } else {
        setState(result);
      }
    });
    return () => {
      active = false;
    };
  }, [attempt]);

  const retry = () => {
    setState({ kind: 'loading' });
    setAttempt((n) => n + 1);
  };

  return (
    <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased">
      <AccountNav current="perfil" />
      <main className="px-gutter-mobile md:px-margin py-space-xl">
        <div className="max-w-3xl mx-auto flex flex-col gap-space-lg">
          <header className="flex flex-col gap-space-xs">
            <span className="font-label-sm text-label-sm uppercase tracking-widest text-primary">Tu cuenta</span>
            <h1 className="font-headline-lg text-headline-lg text-on-surface">Mi perfil</h1>
          </header>

          {(state.kind === 'loading' || state.kind === 'redirecting') && (
            <p role="status" className="font-body-md text-body-md text-on-surface-variant">
              {state.kind === 'loading' ? 'Cargando tu perfil…' : 'Tu sesión venció. Te llevamos al inicio de sesión…'}
            </p>
          )}

          {state.kind === 'ok' && (
            <section className="p-space-md rounded-2xl bg-surface-container-low border border-outline-variant/30 shadow-sm flex flex-col gap-space-md">
              <div className="flex items-center gap-space-md">
                <div className="w-14 h-14 rounded-full bg-primary flex items-center justify-center text-on-primary" aria-hidden="true">
                  <span className="material-symbols-outlined text-[32px]">person</span>
                </div>
                <p className="font-headline-md text-headline-md text-on-surface break-all">{state.profile.username}</p>
              </div>
              <dl>
                <Field label="Nombre de usuario" value={state.profile.username} />
                <Field label="Miembro desde" value={formatDate(state.profile.createdAt)} />
                <Field label="Identificador" value={state.profile.userId} mono />
              </dl>
              <a
                href="/estadisticas"
                className="self-start inline-flex items-center gap-space-xs px-space-md py-space-xs rounded-lg bg-primary text-on-primary font-label-lg text-label-lg shadow-sm hover:bg-primary-container transition-colors"
              >
                <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
                  bar_chart
                </span>
                Ver mis estadísticas
              </a>
            </section>
          )}

          {state.kind === 'not_found' && (
            <Notice
              icon="hourglass_empty"
              title="Tu perfil todavía no está disponible"
              text="Tu sesión es válida, pero el perfil se está creando. Vuelve a intentarlo en unos segundos."
              onRetry={retry}
            />
          )}

          {state.kind === 'unavailable' && (
            <Notice
              icon="cloud_off"
              title="No disponible en este momento"
              text="El servicio de perfiles no respondió. Tu sesión sigue activa."
              onRetry={retry}
            />
          )}
        </div>
      </main>
    </div>
  );
}
