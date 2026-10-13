// Sesión de autenticación en el navegador: mismas claves de localStorage que ya usaba App.tsx.

export interface AuthUser {
  userId: string;
  username: string;
}

export interface AuthSession {
  token: string;
  user: AuthUser;
}

const TOKEN_KEY = 'accessToken';
const USER_KEY = 'user';

/**
 * Fecha de vencimiento (claim `exp`) de un JWT, en milisegundos. No verifica la firma:
 * solo sirve para descartar tokens ya vencidos; quien valida de verdad es el Gateway.
 */
function tokenExpiry(token: string): number | null {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const claims: unknown = JSON.parse(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, '=')));
    const exp = (claims as { exp?: unknown }).exp;
    return typeof exp === 'number' ? exp * 1000 : null;
  } catch {
    return null;
  }
}

export function saveSession(session: AuthSession): void {
  localStorage.setItem(TOKEN_KEY, session.token);
  localStorage.setItem(USER_KEY, JSON.stringify(session.user));
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/**
 * Recupera la sesión guardada al cargar la página. Un token vencido o ilegible se descarta;
 * uno vigente se da por bueno solo hasta que el Gateway diga lo contrario (401 o cierre 4401).
 */
export function loadSession(): AuthSession | null {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const user: unknown = JSON.parse(localStorage.getItem(USER_KEY) ?? 'null');
    const expiry = token ? tokenExpiry(token) : null;
    const validUser =
      typeof user === 'object' &&
      user !== null &&
      typeof (user as AuthUser).userId === 'string' &&
      typeof (user as AuthUser).username === 'string';

    if (token && validUser && expiry !== null && expiry > Date.now()) {
      return { token, user: user as AuthUser };
    }
  } catch {
    // datos corruptos: se tratan como sesión inexistente
  }
  clearSession();
  return null;
}
