import { useEffect, useState } from 'react';
import { navigate } from 'vike/client/router';
import { loginUrl, probeSession } from '../auth/session';
import AccountNav from '../components/AccountNav';
import type { Color, Visibility } from '../game/types';
import { createMatch, describeError, newIdempotencyKey } from './api';
import { MAX_MINUTES, MIN_MINUTES, matchPath } from './types';

export const CREATE_PATH = '/multijugador';

const optionClass = (active: boolean) =>
  `flex-1 text-left p-space-sm rounded-xl border transition-all cursor-pointer ${
    active ? 'bg-primary/10 border-primary shadow-sm' : 'bg-surface-container-low border-outline-variant/40 hover:border-outline'
  }`;

/**
 * /multijugador: crea una partida online (POST /api/matches) y abre su sala de espera en
 * /partida/{matchId}. La Idempotency-Key se genera una vez por configuración: un reintento de la
 * misma creación (por ejemplo, tras un corte de red) reutiliza la misma clave y no duplica partidas.
 */
export default function CreateMatchPage() {
  const [creatorColor, setCreatorColor] = useState<Color>('white');
  const [minutes, setMinutes] = useState(MAX_MINUTES);
  const [visibility, setVisibility] = useState<Visibility>('private');
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sin sesión no tiene sentido mostrar el formulario.
  useEffect(() => {
    void probeSession().then((status) => {
      if (status === 'anonymous') window.location.replace(loginUrl(CREATE_PATH));
    });
  }, []);

  // Cambiar la configuración es otra operación: otra clave (la misma clave con otro cuerpo daría 409).
  const change = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setIdempotencyKey(newIdempotencyKey());
    setError(null);
  };

  const submit = async () => {
    setLoading(true);
    setError(null);
    const result = await createMatch({ creatorColor, timeControl: { minutes }, visibility }, idempotencyKey);
    if (result.ok) {
      await navigate(matchPath(result.value.matchId));
      return;
    }
    setLoading(false);
    if (result.error.code === 'UNAUTHORIZED') {
      window.location.assign(loginUrl(CREATE_PATH));
      return;
    }
    setError(describeError(result.error));
  };

  return (
    <div className="w-full min-h-screen bg-background font-body-md text-on-surface antialiased">
      <AccountNav />
      <main className="px-gutter-mobile md:px-margin py-space-xl">
        <form
          className="max-w-2xl mx-auto flex flex-col gap-space-lg"
          onSubmit={(event) => {
            event.preventDefault();
            if (!loading) void submit();
          }}
        >
          <header className="flex flex-col gap-space-xs">
            <span className="font-label-sm text-label-sm uppercase tracking-widest text-primary">Ajedrez online</span>
            <h1 className="font-headline-lg text-headline-lg text-on-surface">Multijugador online</h1>
            <p className="font-body-md text-body-md text-on-surface-variant">
              Juega contra otra persona desde otro dispositivo. Crea la partida y comparte el enlace de invitación.
            </p>
          </header>

          <fieldset disabled={loading} className="flex flex-col gap-space-xs">
            <legend className="font-label-lg text-label-lg text-on-surface mb-space-xs">Tu color</legend>
            <div className="flex gap-space-sm">
              {(['white', 'black'] as const).map((color) => (
                <button
                  key={color}
                  type="button"
                  aria-pressed={creatorColor === color}
                  onClick={() => change(setCreatorColor)(color)}
                  className={`${optionClass(creatorColor === color)} flex items-center gap-space-sm`}
                >
                  <span className={`w-6 h-6 rounded-full border border-outline ${color === 'white' ? 'bg-[#fdf6ea]' : 'bg-[#2a170c]'}`}></span>
                  <span className="font-label-lg text-label-lg">{color === 'white' ? 'Blancas' : 'Negras'}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset disabled={loading} className="flex flex-col gap-space-xs">
            <legend className="font-label-lg text-label-lg text-on-surface mb-space-xs">Tiempo por jugador</legend>
            <div className="flex items-center gap-space-md">
              <input
                type="range"
                min={MIN_MINUTES}
                max={MAX_MINUTES}
                step={1}
                value={minutes}
                aria-label="Minutos por jugador"
                onChange={(e) => change(setMinutes)(Number(e.target.value))}
                className="flex-1 accent-[#a63605]"
              />
              <span className="font-headline-sm text-headline-sm w-24 text-right">{minutes} min</span>
            </div>
          </fieldset>

          <fieldset disabled={loading} className="flex flex-col gap-space-xs">
            <legend className="font-label-lg text-label-lg text-on-surface mb-space-xs">Visibilidad</legend>
            <div className="flex flex-col sm:flex-row gap-space-sm">
              {(
                [
                  ['private', 'Privada', 'Solo los dos jugadores pueden verla.'],
                  ['shared', 'Compartida', 'Cualquiera con el enlace puede consultarla.'],
                ] as const
              ).map(([value, label, hint]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={visibility === value}
                  onClick={() => change(setVisibility)(value)}
                  className={optionClass(visibility === value)}
                >
                  <span className="block font-label-lg text-label-lg">{label}</span>
                  <span className="block font-body-sm text-body-sm text-on-surface-variant">{hint}</span>
                </button>
              ))}
            </div>
          </fieldset>

          {error && (
            <div role="alert" className="p-space-sm rounded-xl bg-error-container text-on-error-container font-body-sm text-body-sm">
              {error}
            </div>
          )}

          <div className="flex flex-wrap gap-space-sm">
            <button
              type="submit"
              disabled={loading}
              className="px-space-lg py-space-sm rounded-xl bg-primary text-on-primary font-label-lg text-label-lg shadow-md hover:bg-primary-container transition-all flex items-center gap-space-xs cursor-pointer disabled:opacity-70 disabled:cursor-wait"
            >
              <span className={`material-symbols-outlined text-[18px] ${loading ? 'animate-spin' : ''}`}>
                {loading ? 'progress_activity' : 'add_link'}
              </span>
              {loading ? 'Creando partida…' : error ? 'Reintentar' : 'Crear partida'}
            </button>
            <a
              href="/"
              className="px-space-md py-space-sm rounded-xl bg-surface-container-high text-on-surface font-label-lg text-label-lg hover:bg-surface-container-highest transition-colors"
            >
              Cancelar
            </a>
          </div>
        </form>
      </main>
    </div>
  );
}
