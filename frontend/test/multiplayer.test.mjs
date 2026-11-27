// Pruebas del multijugador (src/multiplayer): creación con Idempotency-Key, unión por invitación,
// mensajes del WebSocket, control de turnos, relojes y política de reconexión. Sin servicios.
import assert from 'node:assert/strict';
import { before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { runnerImport } from 'vite';

const load = async (path) =>
  (await runnerImport(fileURLToPath(new URL(path, import.meta.url)), { configFile: false, logLevel: 'silent' })).module;

let api, ms, sock, types;
before(async () => {
  [api, ms, sock, types] = await Promise.all([
    load('../src/multiplayer/api.ts'),
    load('../src/multiplayer/matchSession.ts'),
    load('../src/multiplayer/useMatchSocket.ts'),
    load('../src/multiplayer/types.ts'),
  ]);
});

const A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const MATCH = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';

function fakeFetch(status, body, headers = {}) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    if (status === 'network') throw new TypeError('Failed to fetch');
    return new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json', ...headers },
    });
  };
  return Object.assign(fn, { calls });
}

const state = (over = {}) => ({
  gameId: 'g1',
  matchId: MATCH,
  mode: 'multiplayer',
  visibility: 'private',
  participants: [{ userId: A, color: 'white' }, { userId: B, color: 'black' }],
  botLevel: null,
  timeControl: { minutes: 5 },
  clocks: { white: 300000, black: 300000, turnStartedAt: null, deadline: null },
  status: 'in_progress',
  turn: 'white',
  fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  legalMoves: { e2: ['e3', 'e4'] },
  moves: [],
  drawOffer: null,
  version: 2,
  result: null,
  endReason: null,
  createdAt: '2026-11-03T10:00:00Z',
  finishedAt: null,
  ...over,
});

const reduce = (events, start) => events.reduce(ms.matchReducer, start ?? ms.initialMatchView);
const msg = (message) => ({ type: 'message', message });

describe('crear partida: POST /api/matches', () => {
  const body = { creatorColor: 'white', timeControl: { minutes: 10 }, visibility: 'private' };

  test('envía el cuerpo del contrato y la cabecera Idempotency-Key; devuelve matchId sin gameId', async () => {
    const f = fakeFetch(201, { matchId: MATCH, status: 'waiting', createdAt: '2026-11-03T10:00:00Z' });
    const r = await api.createMatch(body, 'clave-1', f);
    assert.equal(r.ok, true);
    assert.equal(r.value.matchId, MATCH);
    assert.equal(f.calls[0].url, '/api/matches');
    assert.equal(f.calls[0].init.method, 'POST');
    assert.equal(f.calls[0].init.headers['Idempotency-Key'], 'clave-1');
    assert.deepEqual(JSON.parse(f.calls[0].init.body), body);
  });

  test('un reintento con la misma clave se reconoce como repetición (Idempotency-Replayed)', async () => {
    const f = fakeFetch(201, { matchId: MATCH, status: 'waiting', createdAt: 'x' }, { 'Idempotency-Replayed': 'true' });
    const r = await api.createMatch(body, 'clave-1', f);
    assert.equal(r.replayed, true);
  });

  test('errores: sin red, 401, 409 IDEMPOTENCY_KEY_REUSED y 503 con mensajes claros', async () => {
    const net = await api.createMatch(body, 'k', fakeFetch('network'));
    assert.equal(net.error.code, 'NETWORK');
    const unauth = await api.createMatch(body, 'k', fakeFetch(401, { error: { code: 'UNAUTHORIZED', message: 'x' } }));
    assert.equal(unauth.error.code, 'UNAUTHORIZED');
    const reused = await api.createMatch(body, 'k', fakeFetch(409, { error: { code: 'IDEMPOTENCY_KEY_REUSED', message: 'x' } }));
    assert.match(api.describeError(reused.error), /datos distintos/);
    const down = await api.createMatch(body, 'k', fakeFetch(503, { error: { code: 'SERVICES_UNAVAILABLE', message: 'x' } }));
    assert.match(api.describeError(down.error), /no responde/);
  });

  test('claves de idempotencia distintas y con caracteres válidos para el servicio', () => {
    const a = api.newIdempotencyKey();
    const b = api.newIdempotencyKey();
    assert.notEqual(a, b);
    assert.match(a, /^[A-Za-z0-9._:-]{1,128}$/);
  });
});

describe('unirse por invitación: POST /api/matches/{id}/join', () => {
  test('llama directamente al join, sin GET previo, y devuelve el GameState', async () => {
    const f = fakeFetch(200, state());
    const r = await api.joinMatch(MATCH, f);
    assert.equal(r.ok, true);
    assert.equal(f.calls.length, 1);
    assert.equal(f.calls[0].url, `/api/matches/${MATCH}/join`);
    assert.equal(f.calls[0].init.method, 'POST');
  });

  test('partida inexistente, llena, propia y sesión vencida', async () => {
    const cases = [
      [404, 'MATCH_NOT_FOUND', /no existe/],
      [409, 'MATCH_NOT_WAITING', /dos jugadores/],
      [409, 'ALREADY_PARTICIPANT', /creador/],
      [401, 'UNAUTHORIZED', /sesión venció/],
    ];
    for (const [status, code, text] of cases) {
      const r = await api.joinMatch(MATCH, fakeFetch(status, { error: { code, message: 'x' } }));
      assert.equal(r.error.code, code);
      assert.match(api.describeError(r.error), text);
    }
  });

  test('rutas: invitación y partida sin tokens en la URL', () => {
    assert.equal(types.invitePath(MATCH), `/unirse/${MATCH}`);
    assert.equal(types.matchPath(MATCH), `/partida/${MATCH}`);
    assert.equal(types.isMatchId(MATCH), true);
    assert.equal(types.isMatchId('../internal'), false);
  });
});

describe('mensajes del WebSocket', () => {
  test('acepta los diez tipos del servicio y descarta lo desconocido o mal formado', () => {
    const ok = [
      { type: 'state', state: state() },
      { type: 'move_rejected', code: 'VERSION_CONFLICT', message: 'x' },
      { type: 'game_over', result: 'white', endReason: 'checkmate' },
      { type: 'opponent_connected' },
      { type: 'opponent_disconnected', reconnectDeadline: null },
      { type: 'draw_offered', by: 'black' },
      { type: 'draw_declined' },
      { type: 'draw_cancelled' },
      { type: 'error', code: 'NOT_YOUR_TURN', message: 'x' },
      { type: 'pong' },
    ];
    for (const m of ok) assert.ok(sock.parseMatchMessage(JSON.stringify(m)), m.type);
    assert.equal(sock.parseMatchMessage('no json'), null);
    assert.equal(sock.parseMatchMessage(JSON.stringify({ type: 'otro' })), null);
    assert.equal(sock.parseMatchMessage(JSON.stringify({ type: 'state', state: { fen: 'x' } })), null);
  });

  test('una partida en espera sin legalMoves llega con un objeto vacío', () => {
    const waiting = state({ status: 'waiting', participants: [{ userId: A, color: 'white' }] });
    delete waiting.legalMoves;
    const m = sock.parseMatchMessage(JSON.stringify({ type: 'state', state: waiting }));
    assert.deepEqual(m.state.legalMoves, {});
  });

  test('el state del servidor manda; uno más viejo no deshace el tablero', () => {
    const v = reduce([msg({ type: 'state', state: state({ version: 5, fen: 'nuevo' }) }), msg({ type: 'state', state: state({ version: 4, fen: 'viejo' }) })]);
    assert.equal(v.state.fen, 'nuevo');
  });

  test('una jugada rechazada desbloquea sin tocar el tablero', () => {
    const v = reduce([
      { type: 'open' },
      msg({ type: 'state', state: state() }),
      { type: 'sent' },
      msg({ type: 'move_rejected', code: 'ILLEGAL_MOVE', message: 'Jugada ilegal' }),
    ]);
    assert.equal(v.awaitingReply, false);
    assert.equal(v.state.version, 2);
    assert.equal(v.rejection.code, 'ILLEGAL_MOVE');
  });

  test('rival conectado/desconectado, tablas y fin de partida', () => {
    let v = reduce([msg({ type: 'state', state: state() }), msg({ type: 'opponent_disconnected', reconnectDeadline: '2026-11-03T10:01:00Z' })]);
    assert.equal(v.opponentOnline, false);
    assert.equal(v.opponentDeadline, '2026-11-03T10:01:00Z');
    v = ms.matchReducer(v, msg({ type: 'opponent_connected' }));
    assert.equal(v.opponentOnline, true);
    v = ms.matchReducer(v, msg({ type: 'draw_declined' }));
    assert.equal(v.drawNotice, 'declined');
    v = ms.matchReducer(v, msg({ type: 'game_over', result: 'draw', endReason: 'draw' }));
    assert.deepEqual(v.gameOver, { result: 'draw', endReason: 'draw' });
  });

  test('el creador en espera queda registrado como único participante', () => {
    const v = reduce([msg({ type: 'state', state: state({ status: 'waiting', participants: [{ userId: A, color: 'black' }] }) })]);
    assert.equal(v.waitingCreator, A);
  });
});

describe('control de turnos', () => {
  const ready = (over) => reduce([{ type: 'open' }, msg({ type: 'state', state: state(over) })]);

  test('el color sale de participants por userId, no del orden', () => {
    const s = state({ participants: [{ userId: B, color: 'black' }, { userId: A, color: 'white' }] });
    assert.equal(types.colorOf(s, A), 'white');
    assert.equal(types.colorOf(s, B), 'black');
    assert.equal(types.colorOf(s, null), null);
    assert.equal(types.colorOf(s, 'otro'), null);
  });

  test('solo mueve quien tiene el turno, con la partida en curso y sin nada pendiente', () => {
    assert.equal(ms.canMove(ready(), 'white'), true);
    assert.equal(ms.canMove(ready(), 'black'), false);
    assert.equal(ms.canMove(ready({ status: 'waiting' }), 'white'), false);
    assert.equal(ms.canMove(ready({ status: 'finished' }), 'white'), false);
    assert.equal(ms.canMove(ms.matchReducer(ready(), { type: 'sent' }), 'white'), false);
    assert.equal(ms.canMove(ready(), null), false);
    assert.equal(ms.canMove(ms.matchReducer(ready(), { type: 'closed', code: 1006, reason: '', willRetry: true }), 'white'), false);
  });
});

describe('relojes (solo presentación)', () => {
  const now = Date.parse('2026-11-03T10:00:30Z');
  const clocks = { white: 60000, black: 45000, turnStartedAt: '2026-11-03T10:00:00Z', deadline: '2026-11-03T10:01:00Z' };

  test('el bando con turno descuenta hasta el deadline del servidor; el otro queda fijo', () => {
    assert.equal(ms.remainingMs(clocks, 'white', 'in_progress', 'white', now), 30000);
    assert.equal(ms.remainingMs(clocks, 'white', 'in_progress', 'black', now), 45000);
  });

  test('sin deadline usa turnStartedAt; nunca negativo; sin reloj = null', () => {
    assert.equal(ms.remainingMs({ ...clocks, deadline: null }, 'white', 'in_progress', 'white', now), 30000);
    assert.equal(ms.remainingMs(clocks, 'white', 'in_progress', 'white', now + 120000), 0);
    assert.equal(ms.remainingMs(null, 'white', 'in_progress', 'white', now), null);
    assert.equal(ms.remainingMs(clocks, 'white', 'waiting', 'white', now), 60000);
  });

  test('formato m:ss', () => {
    assert.equal(ms.formatClock(600000), '10:00');
    assert.equal(ms.formatClock(61001), '1:02');
    assert.equal(ms.formatClock(0), '0:00');
    assert.equal(ms.formatClock(null), '--:--');
  });
});

describe('reconexión', () => {
  test('reintenta ante cortes de red o reinicios del servidor', () => {
    for (const code of [1001, 1006, 1011, 1012]) assert.equal(ms.shouldReconnect(code, false, 0), true, String(code));
  });

  test('no reintenta: sesión inválida, origen, partida ajena, cierre normal, fin de partida o demasiados intentos', () => {
    for (const code of [4401, 4403, 4404, 1000]) assert.equal(ms.shouldReconnect(code, false, 0), false, String(code));
    assert.equal(ms.shouldReconnect(1006, true, 0), false);
    assert.equal(ms.shouldReconnect(1006, false, ms.MAX_RETRIES), false);
  });

  test('al reconectar se conserva el tablero y no queda nada pendiente', () => {
    const v = reduce([
      { type: 'open' },
      msg({ type: 'state', state: state() }),
      { type: 'sent' },
      { type: 'closed', code: 1006, reason: '', willRetry: true },
      { type: 'connecting' },
    ]);
    assert.equal(v.connection, 'reconnecting');
    assert.equal(v.state.version, 2);
    assert.equal(v.awaitingReply, false);
    assert.equal(v.retries, 1);
    assert.equal(ms.matchReducer(v, { type: 'open' }).retries, 0);
  });

  test('esperas crecientes con tope de 10 s', () => {
    assert.deepEqual([0, 1, 2, 3, 4, 5].map(ms.reconnectDelay), [1000, 2000, 4000, 8000, 10000, 10000]);
  });
});
