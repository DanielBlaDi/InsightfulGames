// Sesión web por cookie (contrato técnico definitivo, 4 y 5.4.4). El JWT vive solo en la cookie
// HttpOnly `session` que pone el gateway: el navegador la envía sola al mismo origen y JavaScript
// no la lee ni la guarda. Todas las funciones son para efectos o manejadores, nunca para renderizar
// en el servidor.

/** Usuario que muestra el encabezado. Nunca incluye el token. */
export interface SessionUser {
  userId: string;
  username: string;
}

/** GET /api/profile/me (sección 8). `createdAt` en ISO 8601 UTC. */
export interface Profile {
  userId: string;
  username: string;
  createdAt: string;
}

/** Resultado de la sonda de sesión: `unavailable` no es lo mismo que "sin sesión". */
export type SessionStatus = 'authenticated' | 'anonymous' | 'unavailable';

export type ProfileResult =
  | { kind: 'ok'; profile: Profile }
  /** 401: la cookie falta, venció o es inválida. */
  | { kind: 'unauthenticated' }
  /** 404 PROFILE_NOT_FOUND: la sesión es válida pero Profile/Stats aún no tiene el perfil. */
  | { kind: 'not_found' }
  /** 503, otros errores o sin red. */
  | { kind: 'unavailable' };

/**
 * Estado de la sesión en el navegador. El JWT vive solo en la cookie HttpOnly `session`; aquí solo
 * se guarda lo que muestra el encabezado. `username` es null si la sesión es válida pero el perfil
 * aún no está disponible (404) o Profile/Stats no responde.
 */
export type SessionState =
  | { status: 'checking' }
  | { status: 'anonymous' }
  | { status: 'unavailable' }
  | { status: 'authenticated'; username: string | null };

type FetchFn = typeof fetch;

const JSON_GET: RequestInit = { credentials: 'same-origin', headers: { Accept: 'application/json' } };

/** Claves que guardaba la versión anterior (JWT en localStorage). Se borran al cargar. */
const LEGACY_KEYS = ['accessToken', 'user'];

export function clearLegacyStorage(storage?: Pick<Storage, 'removeItem'>): void {
  try {
    const target = storage ?? globalThis.localStorage;
    for (const key of LEGACY_KEYS) target?.removeItem(key);
  } catch {
    // almacenamiento bloqueado: no hay nada que limpiar
  }
}

/**
 * ¿Hay sesión? GET /api/stats/me, como pide el contrato (5.4.4): 200 = sí, 401 = no. Un 503 u otro
 * error no dice nada de la sesión: el llamador debe ofrecer reintento, no mandar al login.
 */
export async function probeSession(fetchFn: FetchFn = fetch): Promise<SessionStatus> {
  try {
    const res = await fetchFn('/api/stats/me', JSON_GET);
    if (res.status === 200) return 'authenticated';
    if (res.status === 401) return 'anonymous';
    return 'unavailable';
  } catch {
    return 'unavailable';
  }
}

function isProfile(value: unknown): value is Profile {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.userId === 'string' && typeof v.username === 'string' && typeof v.createdAt === 'string';
}

/** GET /api/profile/me. Distingue 401 (sesión) de 404 (perfil aún no creado) y de fallos del servicio. */
export async function fetchProfile(fetchFn: FetchFn = fetch): Promise<ProfileResult> {
  try {
    const res = await fetchFn('/api/profile/me', JSON_GET);
    if (res.status === 401) return { kind: 'unauthenticated' };
    if (res.status === 404) return { kind: 'not_found' };
    if (!res.ok) return { kind: 'unavailable' };
    const body: unknown = await res.json();
    return isProfile(body) ? { kind: 'ok', profile: body } : { kind: 'unavailable' };
  } catch {
    return { kind: 'unavailable' };
  }
}

/**
 * Estado de la sesión para el encabezado: sonda con /api/stats/me y, si hay sesión, el nombre desde
 * /api/profile/me. Un 404 o 503 del perfil no invalida la sesión: solo deja el nombre en null.
 */
export async function readSession(fetchFn: FetchFn = fetch): Promise<SessionState> {
  const status = await probeSession(fetchFn);
  if (status !== 'authenticated') return { status };
  const profile = await fetchProfile(fetchFn);
  if (profile.kind === 'unauthenticated') return { status: 'anonymous' };
  return { status: 'authenticated', username: profile.kind === 'ok' ? profile.profile.username : null };
}

/** POST /api/auth/logout: el gateway responde 204 y borra la cookie. Devuelve si lo logró. */
export async function logout(fetchFn: FetchFn = fetch): Promise<boolean> {
  try {
    const res = await fetchFn('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
    return res.ok;
  } catch {
    return false;
  }
}

/** Destino del login que devuelve al usuario a `path` después de autenticarse. */
export function loginUrl(path: string): string {
  return `/login?next=${encodeURIComponent(path)}`;
}

/**
 * `next` del login, solo si apunta al propio sitio (evita redirecciones abiertas como
 * next=https://otro.sitio o next=//otro). Sin `next` válido se vuelve al inicio.
 */
export function safeNext(search: string, origin: string): string {
  const next = new URLSearchParams(search).get('next');
  if (!next) return '/';
  try {
    const target = new URL(next, origin);
    return target.origin === origin ? target.pathname + target.search + target.hash : '/';
  } catch {
    return '/';
  }
}
