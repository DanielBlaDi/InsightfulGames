// Pruebas del servidor de producción (server/index.js) contra un gateway simulado.
// Requieren el build: `npm run build && npm test`. Sin dependencias: node:test, http y crypto.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createServer, request } from 'node:http';
import { after, before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';

const SERVER = fileURLToPath(new URL('./index.js', import.meta.url));

const STATS = {
  valid: { gamesPlayed: 5, wins: 3, losses: 1, draws: 1 },
  zero: { gamesPlayed: 0, wins: 0, losses: 0, draws: 0 },
};

/** Gateway web simulado: registra todo lo que recibe. */
function startGateway() {
  const seen = [];
  const server = createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => (body += chunk));
    req.on('end', () => {
      seen.push({ method: req.method, url: req.url, headers: req.headers, body });
      const json = (status, value, headers = {}) => {
        res.writeHead(status, { 'Content-Type': 'application/json', ...headers });
        res.end(JSON.stringify(value));
      };
      const session = /(?:^|;\s*)session=([^;]+)/.exec(req.headers.cookie ?? '')?.[1];
      if (req.url === '/stats/me') {
        if (session === 'down') return json(503, { error: { code: 'SERVICES_UNAVAILABLE', message: 'x' } });
        if (STATS[session]) return json(200, STATS[session]);
        return json(401, { error: { code: 'UNAUTHORIZED', message: 'x' } });
      }
      if (req.url === '/auth/login' && req.method === 'POST') {
        return json(200, { accessToken: 'jwt', expiresIn: 3600, user: { userId: 'u', username: 'ana' } }, {
          'Set-Cookie': 'session=jwt; Max-Age=3600; Path=/; HttpOnly; SameSite=lax',
        });
      }
      if (req.url.startsWith('/matches?') && req.method === 'POST') {
        return json(201, { matchId: 'm', status: 'waiting' }, { 'Idempotency-Replayed': 'true' });
      }
      return json(404, { error: { code: 'NOT_FOUND', message: 'x' } });
    });
  });
  // Handshake WebSocket mínimo (RFC 6455): basta para comprobar que el upgrade llega con sus cabeceras.
  server.on('upgrade', (req, socket) => {
    seen.push({ method: 'UPGRADE', url: req.url, headers: req.headers });
    const accept = createHash('sha1')
      .update(req.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11')
      .digest('base64');
    socket.end(
      `HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`,
    );
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({ server, seen, url: `http://127.0.0.1:${server.address().port}` }));
  });
}

/** Arranca server/index.js en un puerto libre y espera a que escuche. */
function startFrontend(gatewayUrl) {
  return new Promise((resolve, reject) => {
    const probe = createServer().listen(0, '127.0.0.1', () => {
      const { port } = probe.address();
      probe.close(() => {
        const child = spawn(process.execPath, [SERVER], {
          env: { ...process.env, PORT: String(port), API_GATEWAY_URL: gatewayUrl },
          stdio: ['ignore', 'pipe', 'pipe'],
        });
        let output = '';
        const onData = (chunk) => {
          output += chunk;
          if (output.includes('escuchando')) resolve({ child, url: `http://127.0.0.1:${port}`, port });
        };
        child.stdout.on('data', onData);
        child.stderr.on('data', (chunk) => (output += chunk));
        child.on('exit', (code) => reject(new Error(`El servidor terminó (${code}):\n${output}`)));
      });
    });
  });
}

function stop(child) {
  return new Promise((resolve) => {
    child.removeAllListeners('exit');
    child.on('exit', resolve);
    child.kill();
  });
}

const get = (base, path, headers = {}) => fetch(base + path, { headers, redirect: 'manual' });

/** Pide un upgrade WebSocket y devuelve el código de estado de la respuesta. */
function upgrade(port, path, headers = {}) {
  return new Promise((resolve, reject) => {
    const req = request({
      host: '127.0.0.1',
      port,
      path,
      headers: {
        Connection: 'Upgrade',
        Upgrade: 'websocket',
        'Sec-WebSocket-Version': '13',
        'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==',
        ...headers,
      },
    });
    req.on('upgrade', (res, socket) => {
      socket.destroy();
      resolve(res.statusCode);
    });
    req.on('response', (res) => {
      res.resume();
      resolve(res.statusCode);
    });
    req.on('error', reject);
    req.end();
  });
}

describe('servidor del frontend con el gateway disponible', () => {
  let gateway;
  let frontend;
  const internalHits = () => gateway.seen.filter((r) => /internal/i.test(decodeURIComponent(r.url)));

  before(async () => {
    gateway = await startGateway();
    frontend = await startFrontend(gateway.url);
  });
  after(async () => {
    await stop(frontend.child);
    gateway.server.close();
  });

  test('GET /health responde 200 { status: "ok" }', async () => {
    const res = await get(frontend.url, '/health');
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { status: 'ok' });
  });

  test('/estadisticas sin cookie: 302 al login sin llamar al gateway', async () => {
    const before = gateway.seen.length;
    const res = await get(frontend.url, '/estadisticas');
    assert.equal(res.status, 302);
    assert.equal(res.headers.get('location'), '/login?next=%2Festadisticas');
    assert.equal(gateway.seen.length, before);
  });

  test('/estadisticas con sesión: el HTML del servidor ya trae las estadísticas', async () => {
    const res = await get(frontend.url, '/estadisticas', { Cookie: 'otra=1; session=valid' });
    assert.equal(res.status, 200);
    const html = await res.text();
    const root = html.slice(html.indexOf('<div id="root"'));
    for (const value of ['>5<', '>3<', '>1<', 'Victorias', 'Derrotas', 'Tablas']) {
      assert.ok(root.includes(value), `falta ${value} en el HTML renderizado`);
    }
    assert.match(html, /\.pageContext\.json|application\/json/, 'faltan los datos para hidratar');
    const call = gateway.seen.at(-1);
    assert.equal(call.url, '/stats/me');
    assert.equal(call.headers.cookie, 'otra=1; session=valid');
  });

  test('/estadisticas con sesión inválida (401 del gateway): 302 al login', async () => {
    const res = await get(frontend.url, '/estadisticas', { Cookie: 'session=vencida' });
    assert.equal(res.status, 302);
    assert.equal(res.headers.get('location'), '/login?next=%2Festadisticas');
  });

  test('/estadisticas con ceros: muestra los ceros reales y el estado vacío', async () => {
    const html = await (await get(frontend.url, '/estadisticas', { Cookie: 'session=zero' })).text();
    assert.ok(html.includes('Aún no has jugado partidas online'));
    assert.equal((html.match(/>0</g) ?? []).length >= 4, true, 'faltan los cuatro contadores en cero');
  });

  test('/estadisticas con el gateway respondiendo 503: 200 con aviso, sin inventar datos', async () => {
    const res = await get(frontend.url, '/estadisticas', { Cookie: 'session=down' });
    assert.equal(res.status, 200);
    const html = await res.text();
    assert.ok(html.includes('No disponible en este momento'));
    assert.ok(!html.includes('Victorias'));
  });

  test('las demás páginas son de una sola página: el servidor no renderiza su contenido', async () => {
    const res = await get(frontend.url, '/');
    assert.equal(res.status, 200);
    const html = await res.text();
    assert.ok(html.includes('tailwind.config'), 'falta el tema de Tailwind en el <head>');
    assert.match(html, /<html[^>]*lang="es"/);
    assert.match(html, /<div id="root"[^>]*><\/div>/);
  });

  test('/api/internal/* responde 404 en todas sus variantes y nunca llega al gateway', async () => {
    const paths = [
      '/api/internal/logic/users/00000000-0000-0000-0000-000000000001',
      '/API/Internal/auth/account',
      '/api//internal/auth/account',
      '/api/%69nternal/auth/account',
      '/api/games/../internal/auth/account',
      '/api/internal',
      '/api/%E0%A4%A/x',
    ];
    for (const path of paths) {
      for (const method of ['GET', 'POST', 'DELETE']) {
        const res = await fetch(frontend.url + path, { method });
        assert.equal(res.status, 404, `${method} ${path}`);
      }
    }
    assert.deepEqual((await (await fetch(frontend.url + paths[0])).json()).error.code, 'NOT_FOUND');
    assert.deepEqual(internalHits(), []);
  });

  test('REST: quita /api y devuelve Set-Cookie del login', async () => {
    const res = await fetch(`${frontend.url}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'ana', password: 'claveSegura123' }),
    });
    assert.equal(res.status, 200);
    assert.match(res.headers.get('set-cookie'), /^session=jwt;.*HttpOnly/i);
    const call = gateway.seen.at(-1);
    assert.equal(call.url, '/auth/login');
    assert.equal(JSON.parse(call.body).username, 'ana');
  });

  test('REST: reenvía cuerpo, query, Cookie e Idempotency-Key, y devuelve Idempotency-Replayed', async () => {
    const res = await fetch(`${frontend.url}/api/matches?x=1`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Cookie: 'session=valid', 'Idempotency-Key': 'clave-1' },
      body: '{"creatorColor":"white"}',
    });
    assert.equal(res.status, 201);
    assert.equal(res.headers.get('idempotency-replayed'), 'true');
    const call = gateway.seen.at(-1);
    assert.equal(call.url, '/matches?x=1');
    assert.equal(call.headers.cookie, 'session=valid');
    assert.equal(call.headers['idempotency-key'], 'clave-1');
    assert.equal(call.body, '{"creatorColor":"white"}');
  });

  test('REST: los errores del gateway pasan sin cambios', async () => {
    const res = await fetch(`${frontend.url}/api/stats/me`);
    assert.equal(res.status, 401);
    assert.equal((await res.json()).error.code, 'UNAUTHORIZED');
  });

  test('WebSocket: /api/ws/* llega al gateway sin /api, con Origin y Cookie y sin token', async () => {
    const status = await upgrade(frontend.port, '/api/ws/games/abc', {
      Origin: 'http://localhost',
      Cookie: 'session=valid',
    });
    assert.equal(status, 101);
    const call = gateway.seen.at(-1);
    assert.equal(call.method, 'UPGRADE');
    assert.equal(call.url, '/ws/games/abc');
    assert.equal(call.headers.origin, 'http://localhost');
    assert.equal(call.headers.cookie, 'session=valid');
  });

  test('WebSocket: /api/internal/* y rutas que no son /api/ws/* se rechazan con 404', async () => {
    const before = gateway.seen.length;
    assert.equal(await upgrade(frontend.port, '/api/internal/single-player/ws/games/abc'), 404);
    assert.equal(await upgrade(frontend.port, '/api/ws/../internal/x'), 404);
    assert.equal(await upgrade(frontend.port, '/ws/games/abc'), 404);
    assert.equal(gateway.seen.length, before);
  });
});

describe('servidor del frontend con el gateway caído', () => {
  let frontend;

  before(async () => {
    frontend = await startFrontend('http://127.0.0.1:9');
  });
  after(() => stop(frontend.child));

  test('/estadisticas responde 200 con el aviso "no disponible"', async () => {
    const res = await get(frontend.url, '/estadisticas', { Cookie: 'session=valid' });
    assert.equal(res.status, 200);
    assert.ok((await res.text()).includes('No disponible en este momento'));
  });

  test('REST responde 503 SERVICES_UNAVAILABLE y el servidor sigue atendiendo', async () => {
    const res = await fetch(`${frontend.url}/api/stats/me`);
    assert.equal(res.status, 503);
    assert.equal((await res.json()).error.code, 'SERVICES_UNAVAILABLE');
    assert.equal((await get(frontend.url, '/health')).status, 200);
  });
});
