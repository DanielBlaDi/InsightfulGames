// Inicio de sesión a ritmo constante por encima del límite de los reverse proxies (10 peticiones/s por IP,
// ráfaga de 20). Mide qué parte frena el proxy (429), cuántos intentos por segundo llegan a Auth y cuánto
// tarda cada respuesta.
//
//   k6 run -e TASA=20 --out csv=performance/resultados/login.csv.gz performance/k6/login-limite.js
//
// Todas las peticiones salen del mismo equipo (una sola IP), igual que en la prueba de fuerza bruta del
// escenario de seguridad 2, pero con credenciales correctas.
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import { MOVIL, CLAVE } from './lib/comun.js';

const usuarios = new SharedArray('usuarios', () => JSON.parse(open('../resultados/usuarios.json')));
const TASA = Number(__ENV.TASA || 20);

// 429 es la respuesta esperada al pasar el límite: no cuenta como fallo
http.setResponseCallback(http.expectedStatuses(200, 429));

export const options = {
  scenarios: {
    login: {
      executor: 'constant-arrival-rate', rate: TASA, timeUnit: '1s', duration: '60s',
      preAllocatedVUs: TASA, maxVUs: TASA * 3, tags: { canal: 'movil' },
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{status:200}': ['p(95)<1000'],
    'http_req_duration{status:429}': ['p(95)<200'],
    'http_reqs{status:200}': ['count>=0'],
    'http_reqs{status:429}': ['count>=0'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  const u = usuarios[Math.floor(Math.random() * usuarios.length)];
  const r = http.post(`${MOVIL}/auth/login`, JSON.stringify({ username: u.username, password: CLAVE }), {
    headers: { 'Content-Type': 'application/json' },
    tags: { name: 'POST /auth/login', tipo: 'login' },
  });
  check(r, { 'login: 200 o 429': (x) => x.status === 200 || x.status === 429 });
}

export function handleSummary(data) {
  const m = data.metrics;
  const n = (k) => (m[k] ? m[k].values.count : 0);
  const total = n('http_reqs');
  const txt = `\n== login a ${TASA}/s: ${total} intentos, ${n('http_reqs{status:200}')} entraron (200), `
    + `${n('http_reqs{status:429}')} frenados por el proxy (429)\n`;
  return { stdout: txt, 'performance/resultados/login-resumen.json': JSON.stringify(data, null, 1) };
}
