// Recorridos de usuarios reales de la web y de la app, con cuatro perfiles de carga.
//
//   k6 run -e PERFIL=humo|carga|estres|pico --out csv=performance/resultados/<perfil>.csv.gz performance/k6/flujos.js
//
// Necesita performance/resultados/usuarios.json (lo genera preparar.js). Reparto: 60 % de los usuarios virtuales
// navegan la web y 40 % usan la app móvil. Cada usuario hace pausas de 1 a 3 s entre acciones (think time).
import http from 'k6/http';
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import { WEB, MOVIL, APERTURA, pausa, conBearer, conCookie, leerJson, escalar } from './lib/comun.js';

const usuarios = new SharedArray('usuarios', () => JSON.parse(open('../resultados/usuarios.json')));

const PERFIL = __ENV.PERFIL || 'humo';
const ETAPAS = {
  humo: [{ duration: '1m', target: 1 }],
  carga: [{ duration: '1m', target: 40 }, { duration: '5m', target: 40 }, { duration: '30s', target: 0 }],
  estres: [
    { duration: '1m', target: 50 }, { duration: '2m', target: 50 },
    { duration: '1m', target: 100 }, { duration: '2m', target: 100 },
    { duration: '1m', target: 200 }, { duration: '2m', target: 200 },
    { duration: '1m', target: 300 }, { duration: '2m', target: 300 },
    { duration: '30s', target: 0 },
  ],
  pico: [
    { duration: '30s', target: 10 }, { duration: '10s', target: 200 }, { duration: '1m', target: 200 },
    { duration: '10s', target: 10 }, { duration: '1m', target: 10 }, { duration: '10s', target: 0 },
  ],
}[PERFIL];
if (!ETAPAS) throw new Error(`PERFIL desconocido: ${PERFIL} (humo, carga, estres, pico)`);

const humo = PERFIL === 'humo';

export const options = {
  scenarios: {
    web: {
      executor: 'ramping-vus', exec: 'web', startVUs: humo ? 1 : 0,
      stages: humo ? ETAPAS : escalar(ETAPAS, 0.6), gracefulRampDown: '30s', tags: { canal: 'web' },
    },
    movil: {
      executor: 'ramping-vus', exec: 'movil', startVUs: humo ? 1 : 0,
      stages: humo ? ETAPAS : escalar(ETAPAS, 0.4), gracefulRampDown: '30s', tags: { canal: 'movil' },
    },
  },
  // Objetivos (SLO) propuestos para la operación normal. En estrés y pico se espera que alguno falle:
  // el informe registra en qué nivel de carga deja de cumplirse.
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
    'http_req_duration{tipo:pagina}': ['p(95)<1000'],
    'http_req_duration{tipo:lectura}': ['p(95)<500'],
    'http_req_duration{tipo:escritura}': ['p(95)<800'],
    'http_req_duration{canal:web}': ['p(95)<1000'],
    'http_req_duration{canal:movil}': ['p(95)<800'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

function usuario() {
  return usuarios[(__VU - 1) % usuarios.length];
}

function detalleDe(items, canal) {
  const p = (items || []).find((g) => g.mode !== 'multiplayer') || null;
  if (!p) return null;
  return canal === 'web' ? `/api/games/${p.gameId}` : `/games/${p.gameId}`;
}

// --------------------------------------------------------------------------------------- web
export function web() {
  const u = usuario();
  const pag = (nombre) => conCookie(u.token, { name: nombre, tipo: 'pagina' });
  const api = (nombre) => conCookie(u.token, { name: nombre, tipo: 'lectura' });

  let r = http.get(`${WEB}/`, pag('GET /'));
  check(r, { 'web: inicio 200': (x) => x.status === 200 });
  pausa();

  r = http.get(`${WEB}/historial`, pag('GET /historial'));
  check(r, { 'web: historial 200': (x) => x.status === 200 });
  // Lo que pide el navegador al abrir el historial (en paralelo, como hace el frontend)
  const [perfil, stats, lista] = http.batch([
    ['GET', `${WEB}/api/profile/me`, null, api('GET /api/profile/me')],
    ['GET', `${WEB}/api/stats/me`, null, api('GET /api/stats/me')],
    ['GET', `${WEB}/api/games?limit=20`, null, api('GET /api/games')],
  ]);
  check(perfil, { 'web: perfil 200': (x) => x.status === 200 });
  check(stats, { 'web: estadísticas 200': (x) => x.status === 200 });
  check(lista, { 'web: lista 200': (x) => x.status === 200 });
  pausa();

  const ruta = detalleDe(leerJson(lista, 'items'), 'web');
  if (ruta) {
    r = http.get(`${WEB}${ruta}`, api('GET /api/games/{id}'));
    check(r, { 'web: detalle 200': (x) => x.status === 200 });
    pausa();
  }

  r = http.get(`${WEB}/estadisticas`, pag('GET /estadisticas'));
  check(r, { 'web: página estadísticas 200': (x) => x.status === 200 });
  pausa();
}

// ------------------------------------------------------------------------------------- móvil
export function movil() {
  const u = usuario();
  const lect = (nombre) => conBearer(u.token, { name: nombre, tipo: 'lectura' });
  const escr = (nombre) => conBearer(u.token, { name: nombre, tipo: 'escritura' });

  let r = http.get(`${MOVIL}/home`, lect('GET /home'));
  check(r, { 'móvil: inicio 200': (x) => x.status === 200 && (leerJson(x, 'unavailable') || []).length === 0 });
  pausa();

  const lista = http.get(`${MOVIL}/games?limit=20`, lect('GET /games'));
  check(lista, { 'móvil: historial 200': (x) => x.status === 200 });
  const ruta = detalleDe(leerJson(lista, 'items'), 'movil');
  if (ruta) {
    r = http.get(`${MOVIL}${ruta}`, lect('GET /games/{id}'));
    check(r, { 'móvil: detalle 200': (x) => x.status === 200 });
  }
  pausa();

  // 30 % de las sesiones juegan una partida local corta (camino de escritura: Game Logic + hub)
  if (Math.random() < 0.3) {
    r = http.post(`${MOVIL}/games`, JSON.stringify({ mode: 'local', timeControl: null }), escr('POST /games'));
    if (check(r, { 'móvil: crear partida 201': (x) => x.status === 201 })) {
      let estado = r.json();
      for (const uci of APERTURA) {
        pausa(0.5, 1.5);
        r = http.post(`${MOVIL}/games/${estado.gameId}/moves`,
          JSON.stringify({ uci, expectedVersion: estado.version }), escr('POST /games/{id}/moves'));
        if (!check(r, { 'móvil: jugada 200': (x) => x.status === 200 })) break;
        estado = r.json();
      }
      r = http.post(`${MOVIL}/games/${estado.gameId}/resign`, JSON.stringify({ side: 'white' }),
        escr('POST /games/{id}/resign'));
      check(r, { 'móvil: rendición 200': (x) => x.status === 200 });
    }
    pausa();
  }

  r = http.get(`${MOVIL}/stats/me`, lect('GET /stats/me'));
  check(r, { 'móvil: estadísticas 200': (x) => x.status === 200 });
  pausa();
}

// ----------------------------------------------------------------------------------- resumen
function linea(data, nombre, etiqueta) {
  const m = data.metrics[nombre];
  if (!m) return '';
  const v = m.values;
  const umbral = m.thresholds ? Object.entries(m.thresholds).map(([k, t]) => `${k} ${t.ok ? 'OK' : 'NO CUMPLE'}`).join(', ') : '';
  return `  ${etiqueta.padEnd(28)} p50 ${v.med.toFixed(0)} ms · p95 ${v['p(95)'].toFixed(0)} ms · p99 ${v['p(99)'].toFixed(0)} ms ${umbral ? `[${umbral}]` : ''}\n`;
}

export function handleSummary(data) {
  const m = data.metrics;
  let txt = `\n== ${PERFIL}: ${m.http_reqs.values.count} peticiones (${m.http_reqs.values.rate.toFixed(1)}/s), `;
  txt += `fallidas ${(m.http_req_failed.values.rate * 100).toFixed(2)} %, checks ${(m.checks.values.rate * 100).toFixed(2)} %\n`;
  txt += linea(data, 'http_req_duration{tipo:pagina}', 'páginas (SSR)');
  txt += linea(data, 'http_req_duration{tipo:lectura}', 'API lecturas');
  txt += linea(data, 'http_req_duration{tipo:escritura}', 'API escrituras');
  txt += linea(data, 'http_req_duration{canal:web}', 'canal web');
  txt += linea(data, 'http_req_duration{canal:movil}', 'canal móvil');
  return { stdout: txt, [`performance/resultados/${PERFIL}-resumen.json`]: JSON.stringify(data, null, 1) };
}
