import { useEffect, useState } from 'react';
import { fetchProfile, loginUrl } from '../auth/session';

export type Identity =
  | { status: 'loading' }
  | { status: 'ok'; userId: string; username: string }
  /** Sesión válida pero sin perfil (404) o Profile/Stats caído: no se inventa un userId. */
  | { status: 'unknown'; reason: 'not_found' | 'unavailable' };

/**
 * Usuario actual para saber qué color juega: GET /api/profile/me (el JWT no se lee nunca).
 * Sin sesión (401) manda al login con `next` = la ruta actual.
 */
export function useIdentity(returnPath: string): Identity {
  const [identity, setIdentity] = useState<Identity>({ status: 'loading' });
  useEffect(() => {
    let active = true;
    void fetchProfile().then((result) => {
      if (!active) return;
      if (result.kind === 'unauthenticated') {
        window.location.replace(loginUrl(returnPath));
      } else if (result.kind === 'ok') {
        setIdentity({ status: 'ok', userId: result.profile.userId, username: result.profile.username });
      } else {
        setIdentity({ status: 'unknown', reason: result.kind });
      }
    });
    return () => {
      active = false;
    };
  }, [returnPath]);
  return identity;
}
