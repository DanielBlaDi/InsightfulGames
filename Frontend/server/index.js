// Servidor web del frontend (contrato técnico definitivo, 5.4.1): un solo proceso Node con
// Express y Vike, sin Nginx. Orden de resolución:
//   1. GET /health
//   2. /api/internal/*  -> 404, antes de cualquier proxy
//   3. /api/ws/*        -> proxy WebSocket al gateway web, sin /api, con Origin y Cookie
//   4. /api/*           -> proxy REST al gateway web, sin /api, con Set-Cookie, Cookie e Idempotency-Key
//   5. el resto         -> archivos del build y páginas de Vike
// El servidor no valida JWT: lo hace el gateway.
import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isInternalApiPath, isSocketApiPath } from './routes.js';

// React y Vike leen NODE_ENV al cargarse; por eso vike/server se importa después.
process.env.NODE_ENV ??= 'production';
const { renderPage } = await import('vike/server');

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
// El contenedor escucha siempre en 80 (FRONTEND_PORT solo cambia el puerto publicado).
// PORT existe para ejecutar el servidor fuera de Docker y en las pruebas.
const port = Number(process.env.PORT ?? 80);
const gatewayUrl = process.env.API_GATEWAY_URL;
if (!gatewayUrl) {
  console.error('API_GATEWAY_URL es obligatoria, por ejemplo http://api-gateway-component:8080');
  process.exit(1);
}

const errorBody = (code, message) => ({ error: { code, message } });

/** Gateway caído: 503 al navegador, sin tumbar el servidor. En WebSocket res es el socket. */
function onProxyError(err, _req, res) {
  console.warn(`Gateway no disponible: ${err.code ?? err.message}`);
  if (typeof res.writeHead !== 'function') {
    res.destroy();
    return;
  }
  if (!res.headersSent) {
    res.writeHead(503, { 'Content-Type': 'application/json' });
  }
  res.end(JSON.stringify(errorBody('SERVICES_UNAVAILABLE', 'El gateway no responde')));
}

// REST. Montado en /api, Express ya entrega la ruta sin el prefijo. Las cabeceras pasan tal
// cual en los dos sentidos. El tiempo máximo cubre DELETE /auth/account (4 × HTTP_TIMEOUT).
const restProxy = createProxyMiddleware({
  target: gatewayUrl,
  changeOrigin: true,
  xfwd: true,
  proxyTimeout: 65_000,
  on: { error: onProxyError },
});

// WebSocket. Solo se usa desde el evento upgrade (abajo). Sin changeOrigin: Origin y Host del
// navegador llegan al gateway, que valida Origin contra WS_ALLOWED_ORIGINS.
const socketProxy = createProxyMiddleware({
  target: gatewayUrl,
  ws: true,
  pathFilter: (path) => isSocketApiPath(path),
  pathRewrite: { '^/api': '' },
  on: { error: onProxyError },
});

const app = express();
app.disable('x-powered-by');

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

app.use((req, res, next) => {
  if (isInternalApiPath(req.url)) {
    res.status(404).json(errorBody('NOT_FOUND', 'Ruta inexistente'));
    return;
  }
  next();
});

app.use('/api', restProxy);

app.use(express.static(join(root, 'dist', 'client'), { index: false }));

app.use(async (req, res, next) => {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    next();
    return;
  }
  try {
    const { httpResponse } = await renderPage({
      urlOriginal: req.originalUrl,
      headersOriginal: req.headers,
    });
    if (!httpResponse) {
      next();
      return;
    }
    for (const [name, value] of httpResponse.headers) res.setHeader(name, value);
    res.status(httpResponse.statusCode);
    httpResponse.pipe(res);
  } catch (err) {
    next(err);
  }
});

const server = app.listen(port, () => {
  console.log(`Frontend escuchando en el puerto ${port}; gateway: ${gatewayUrl}`);
});

server.on('upgrade', (req, socket, head) => {
  if (isInternalApiPath(req.url) || !isSocketApiPath(req.url)) {
    socket.end('HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n');
    return;
  }
  socketProxy.upgrade(req, socket, head);
});

// Docker para el contenedor con SIGTERM; Node como PID 1 no termina solo.
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
    server.closeAllConnections();
  });
}
