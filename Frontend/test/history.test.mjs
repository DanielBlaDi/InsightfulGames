import assert from 'node:assert/strict';
import { before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { runnerImport } from 'vite';

const load = async (path) =>
  (await runnerImport(fileURLToPath(new URL(path, import.meta.url)), { configFile: false, logLevel: 'silent' })).module;

let api;
before(async () => {
  api = await load('../src/history/api.ts');
});

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

describe('historial de partidas: GET /api/games (sección 4.2)', () => {
  const sampleGame = {
    gameId: '11111111-1111-4111-8111-111111111111',
    mode: 'multiplayer',
    status: 'finished',
    result: 'white',
    createdAt: '2026-11-02T12:00:00Z',
    matchId: '22222222-2222-4222-8222-222222222222',
  };

  test('200 = entrega GamesPage con items y nextCursor', async () => {
    const f = fakeFetch(200, { items: [sampleGame], nextCursor: 'Mg' });
    const res = await api.fetchGameHistory(null, 20, f);
    assert.equal(res.kind, 'ok');
    assert.equal(res.page.items.length, 1);
    assert.equal(res.page.nextCursor, 'Mg');
    assert.equal(f.calls[0].url, '/api/games?limit=20');
    assert.equal(f.calls[0].init.credentials, 'same-origin');
  });

  test('envía cursor cuando se solicita la siguiente página', async () => {
    const f = fakeFetch(200, { items: [sampleGame], nextCursor: null });
    const res = await api.fetchGameHistory('Mg', 20, f);
    assert.equal(res.kind, 'ok');
    assert.equal(f.calls[0].url, '/api/games?limit=20&cursor=Mg');
  });

  test('401 = no autenticado', async () => {
    const f = fakeFetch(401, { error: { code: 'UNAUTHORIZED', message: 'No hay sesión' } });
    const res = await api.fetchGameHistory(null, 20, f);
    assert.equal(res.kind, 'unauthenticated');
  });

  test('503 o fallo de red = no disponible', async () => {
    const f1 = fakeFetch(503, { error: { code: 'SERVICES_UNAVAILABLE', message: 'Caído' } });
    assert.equal((await api.fetchGameHistory(null, 20, f1)).kind, 'unavailable');

    const f2 = fakeFetch('network');
    assert.equal((await api.fetchGameHistory(null, 20, f2)).kind, 'unavailable');
  });

  test('cuerpo inválido = no disponible', async () => {
    const f = fakeFetch(200, { invalid: true });
    assert.equal((await api.fetchGameHistory(null, 20, f)).kind, 'unavailable');
  });
});

