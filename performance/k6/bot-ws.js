// Partidas contra el bot por WebSocket (WSS) con concurrencia creciente: 1, 2, 4, 8 y 12 partidas simultáneas.
//
//   k6 run --out csv=performance/resultados/bot.csv.gz performance/k6/bot-ws.js
//
// Cada usuario virtual crea una partida vs_bot por REST, se conecta a wss://.../api/ws/games/{id} y juega
// JUGADAS jugadas legales al azar, pensando de 1 a 3 s cada una (como una persona). Mide:
//   bot_respuesta       ms desde que envía su jugada hasta recibir la del bot (incluye ~0,5 s de motor)
//   ws_jugada_aplicada  ms hasta que el servidor confirma la jugada humana (state con la versión nueva)
//   bot_jugada_ok       proporción de jugadas del bot que llegan (falla si el gateway avisa un error, p. ej. ENGINE_BUSY)
// Todas las métricas llevan la etiqueta concurrencia = partidas activas al empezar la partida.
import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';
import { WebSocket } from 'k6/websockets';
import { setTimeout, clearTimeout } from 'k6/timers';
import { Trend, Rate, Counter } from 'k6/metrics';
import { SharedArray } from 'k6/data';
import { WEB, WS_WEB, ORIGEN, conCookie, jugadaAleatoria } from './lib/comun.js';

const usuarios = new SharedArray('usuarios', () => JSON.parse(open('../resultados/usuarios.json')));

const respuestaBot = new Trend('bot_respuesta', true);
const jugadaAplicada = new Trend('ws_jugada_aplicada', true);
const jugadaBotOk = new Rate('bot_jugada_ok');
const partidaOk = new Rate('bot_partida_ok');
const errores = new Counter('bot_errores');

const JUGADAS = Number(__ENV.JUGADAS || 8);
const NIVEL = Number(__ENV.BOT_NIVEL || 5);
const NIVELES = (__ENV.CONCURRENCIA || '1,2,4,8,12').split(',').map(Number);
const POR_NIVEL = __ENV.DURACION_NIVEL || '85s';

const etapas = [];
for (const n of NIVELES) {
  etapas.push({ duration: '5s', target: n }, { duration: POR_NIVEL, target: n });
}
etapas.push({ duration: '10s', target: 0 });

export const options = {
  scenarios: {
    bot: { executor: 'ramping-vus', startVUs: 0, stages: etapas, gracefulRampDown: '60s', tags: { canal: 'web' } },
  },
  thresholds: {
    bot_respuesta: ['p(95)<3000'],
    bot_jugada_ok: ['rate>0.99'],
    bot_partida_ok: ['rate>0.95'],
    ws_jugada_aplicada: ['p(95)<500'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  const u = usuarios[usuarios.length - 1 - ((__VU - 1) % usuarios.length)];
  const concurrencia = String(exec.instance.vusActive);
  const tags = { concurrencia };

  const r = http.post(`${WEB}/api/games`, JSON.stringify({ mode: 'vs_bot', botLevel: NIVEL, playerColor: 'white' }),
    conCookie(u.token, { name: 'POST /api/games (vs_bot)', tipo: 'escritura' }));
  if (!check(r, { 'bot: crear partida 201': (x) => x.status === 201 })) {
    errores.add(1, { ...tags, motivo: `crear-${r.status}` });
    partidaOk.add(false, tags);
    return;
  }
  const gameId = r.json('gameId');

  const ws = new WebSocket(`${WS_WEB}/api/ws/games/${gameId}`, null, {
    headers: { Cookie: `session=${u.token}`, Origin: ORIGEN },
    tags: { name: 'WSS /api/ws/games/{id}' },
  });

  let enviadas = 0;
  let enviadoEn = 0;
  let versionEsperada = Infinity; // versión con la jugada del bot ya aplicada
  let confirmada = false;
  let terminado = false;
  let temporizador = null;

  const guardia = setTimeout(() => {
    errores.add(1, { ...tags, motivo: 'sin-respuesta-60s' });
    terminar(false);
  }, 60000);

  function terminar(ok, estado) {
    if (terminado) return;
    terminado = true;
    clearTimeout(guardia);
    if (temporizador) clearTimeout(temporizador);
    partidaOk.add(ok, tags);
    if (!estado || estado.status !== 'finished') {
      // Se deja la partida terminada para no acumular partidas abiertas
      http.post(`${WEB}/api/games/${gameId}/resign`, null,
        conCookie(u.token, { name: 'POST /api/games/{id}/resign', tipo: 'escritura' }));
    }
    ws.close();
  }

  function jugar(estado) {
    if (enviadas >= JUGADAS || estado.status === 'finished') {
      terminar(true, estado);
      return;
    }
    const uci = jugadaAleatoria(estado);
    if (!uci) {
      terminar(true, estado);
      return;
    }
    // Una persona piensa su jugada: 1 a 3 s
    temporizador = setTimeout(() => {
      temporizador = null;
      versionEsperada = estado.version + 2; // +1 la jugada humana, +1 la del bot
      confirmada = false;
      enviadoEn = Date.now();
      enviadas += 1;
      ws.send(JSON.stringify({ type: 'move', uci, expectedVersion: estado.version }));
    }, 1000 + Math.random() * 2000);
  }

  ws.onmessage = (e) => {
    let m;
    try {
      m = JSON.parse(e.data);
    } catch (err) {
      return;
    }
    if (m.type === 'state' && m.state) {
      const estado = m.state;
      if (enviadas === 0 && versionEsperada === Infinity && !temporizador) {
        jugar(estado); // primer state al conectarse
        return;
      }
      if (!confirmada && estado.version >= versionEsperada - 1) {
        jugadaAplicada.add(Date.now() - enviadoEn, tags);
        confirmada = true;
      }
      if (estado.version >= versionEsperada) {
        respuestaBot.add(Date.now() - enviadoEn, tags);
        jugadaBotOk.add(true, tags);
        versionEsperada = Infinity;
        jugar(estado);
      } else if (estado.status === 'finished') {
        terminar(true, estado);
      }
    } else if (m.type === 'error' || m.type === 'move_rejected') {
      // p. ej. ENGINE_BUSY: Botcito no tenía un motor libre y la jugada del bot no se hizo
      errores.add(1, { ...tags, motivo: m.code || m.type });
      if (versionEsperada !== Infinity) jugadaBotOk.add(false, tags);
      terminar(false);
    }
  };
  ws.onerror = () => {
    errores.add(1, { ...tags, motivo: 'ws' });
    terminar(false);
  };
}

export function handleSummary(data) {
  const m = data.metrics;
  const v = (n) => (m[n] ? m[n].values : null);
  let txt = '\n== bot por WebSocket\n';
  if (v('bot_respuesta')) {
    txt += `  respuesta del bot  p50 ${v('bot_respuesta').med.toFixed(0)} ms · p95 ${v('bot_respuesta')['p(95)'].toFixed(0)} ms\n`;
  }
  if (v('bot_jugada_ok')) txt += `  jugadas del bot OK ${(v('bot_jugada_ok').rate * 100).toFixed(1)} %\n`;
  if (v('bot_partida_ok')) txt += `  partidas completas ${(v('bot_partida_ok').rate * 100).toFixed(1)} %\n`;
  return { stdout: txt, 'performance/resultados/bot-resumen.json': JSON.stringify(data, null, 1) };
}
