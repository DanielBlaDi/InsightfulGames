// Pruebas de src/auth/session.ts (sesión web por cookie). Carga el TypeScript con runnerImport de
// Vite y simula fetch: no necesitan el build ni servicios. `npm test` las ejecuta junto a las del
// servidor.
import assert from 'node:assert/strict';
import { before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { runnerImport } from 'vite';

const SESSION = fileURLToPath(new URL('../src/auth/session.ts', import.meta.url));

let s;
before(async () => {
  ({ module: s } = await runnerImport(SESSION, { configFile: false, logLevel: 'silent' }));
});

/** fetch simulado: responde `status` con `body` y anota cada llamada. */
function fakeFetch(status, body) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    if (status === 'network') throw new TypeError('Failed to fetch');
    return new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  return Object.assign(fn, { calls });
}

const err = (code) => ({ error: { code, message: 'x' } });

describe('sonda de sesión: GET /api/stats/me (5.4.4)', () => {
  test('200 = con sesión; usa la cookie del mismo origen y no envía Authorization', async () => {
    const f = fakeFetch(200, { gamesPlayed: 0, wins: 0, losses: 0, draws: 0 });
    assert.equal(await s.probeSession(f), 'authenticated');
    assert.equal(f.calls[0].url, '/api/stats/me');
    assert.equal(f.calls[0].init.credentials, 'same-origin');
    assert.equal(f.calls[0].init.headers.Authorization, undefined);
  });

  test('401 = sin sesión', async () => {
    assert.equal(await s.probeSession(fakeFetch(401, err('UNAUTHORIZED'))), 'anonymous');
  });

  test('503, 404 o sin red = no disponible (no se trata como sesión inválida)', async () => {
    assert.equal(await s.probeSession(fakeFetch(503, err('SERVICES_UNAVAILABLE'))), 'unavailable');
    assert.equal(await s.probeSession(fakeFetch(404, err('NOT_FOUND'))), 'unavailable');
    assert.equal(await s.probeSession(fakeFetch('network')), 'unavailable');
  });
});

describe('perfil: GET /api/profile/me', () => {
  const profile = { userId: '7c0e0b9e-0000-4000-8000-000000000001', username: 'ana', createdAt: '2026-11-01T10:00:00Z' };

  test('200 con el perfil del backend', async () => {
    const f = fakeFetch(200, profile);
    assert.deepEqual(await s.fetchProfile(f), { kind: 'ok', profile });
    assert.equal(f.calls[0].url, '/api/profile/me');
  });

  test('401 = sesión inválida', async () => {
    assert.deepEqual(await s.fetchProfile(fakeFetch(401, err('UNAUTHORIZED'))), { kind: 'unauthenticated' });
  });

  test('404 PROFILE_NOT_FOUND = perfil aún no creado, no sesión inválida', async () => {
    assert.deepEqual(await s.fetchProfile(fakeFetch(404, err('PROFILE_NOT_FOUND'))), { kind: 'not_found' });
  });

  test('503, respuesta con forma inesperada o sin red = no disponible', async () => {
    assert.deepEqual(await s.fetchProfile(fakeFetch(503, err('SERVICES_UNAVAILABLE'))), { kind: 'unavailable' });
    assert.deepEqual(await s.fetchProfile(fakeFetch(200, { username: 'ana' })), { kind: 'unavailable' });
    assert.deepEqual(await s.fetchProfile(fakeFetch('network')), { kind: 'unavailable' });
  });
});

describe('estado del encabezado: readSession', () => {
  /** fetch simulado por ruta: { '/api/stats/me': status, '/api/profile/me': [status, body] }. */
  const routes = (table) => async (url) => {
    const [status, body] = [].concat(table[url]);
    return new Response(body ? JSON.stringify(body) : null, { status });
  };
  const stats = [200, { gamesPlayed: 0, wins: 0, losses: 0, draws: 0 }];
  const profile = [200, { userId: 'u', username: 'ana', createdAt: '2026-11-01T10:00:00Z' }];

  test('con sesión y perfil: muestra el nombre', async () => {
    const state = await s.readSession(routes({ '/api/stats/me': stats, '/api/profile/me': profile }));
    assert.deepEqual(state, { status: 'authenticated', username: 'ana' });
  });

  test('sin sesión (401): anónimo, sin pedir el perfil', async () => {
    let profileCalls = 0;
    const f = async (url) => {
      if (url === '/api/profile/me') profileCalls++;
      return new Response(null, { status: 401 });
    };
    assert.deepEqual(await s.readSession(f), { status: 'anonymous' });
    assert.equal(profileCalls, 0);
  });

  test('perfil 404 o 503: la sesión sigue activa, sin nombre', async () => {
    for (const code of [404, 503]) {
      const state = await s.readSession(routes({ '/api/stats/me': stats, '/api/profile/me': code }));
      assert.deepEqual(state, { status: 'authenticated', username: null }, String(code));
    }
  });

  test('stats 503: no disponible (no se manda al login)', async () => {
    assert.deepEqual(await s.readSession(routes({ '/api/stats/me': 503 })), { status: 'unavailable' });
  });
});

describe('logout: POST /api/auth/logout', () => {
  test('204 = sesión cerrada', async () => {
    const f = fakeFetch(204);
    assert.equal(await s.logout(f), true);
    assert.equal(f.calls[0].url, '/api/auth/logout');
    assert.equal(f.calls[0].init.method, 'POST');
  });

  test('error o sin red = no cerrada', async () => {
    assert.equal(await s.logout(fakeFetch(503, err('SERVICES_UNAVAILABLE'))), false);
    assert.equal(await s.logout(fakeFetch('network')), false);
  });
});

describe('navegación del login', () => {
  const origin = 'http://localhost';

  test('loginUrl codifica la ruta de vuelta', () => {
    assert.equal(s.loginUrl('/perfil'), '/login?next=%2Fperfil');
    assert.equal(s.loginUrl('/estadisticas'), '/login?next=%2Festadisticas');
  });

  test('safeNext vuelve a /perfil o /estadisticas', () => {
    assert.equal(s.safeNext('?next=%2Fperfil', origin), '/perfil');
    assert.equal(s.safeNext('?next=/estadisticas', origin), '/estadisticas');
  });

  test('safeNext rechaza otros orígenes y vuelve al inicio sin next', () => {
    for (const search of ['?next=https://otro.sitio/x', '?next=//otro.sitio', '?next=http://[', '']) {
      assert.equal(s.safeNext(search, origin), '/', search);
    }
  });
});

describe('limpieza de la sesión antigua en localStorage', () => {
  test('borra accessToken y user', () => {
    const removed = [];
    s.clearLegacyStorage({ removeItem: (k) => removed.push(k) });
    assert.deepEqual(removed, ['accessToken', 'user']);
  });

  test('no falla si el almacenamiento está bloqueado o no existe', () => {
    assert.doesNotThrow(() =>
      s.clearLegacyStorage({
        removeItem: () => {
          throw new Error('SecurityError');
        },
      }),
    );
    assert.doesNotThrow(() => s.clearLegacyStorage(undefined));
  });
});
