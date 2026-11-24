// Prepara los usuarios de prueba: los registra si no existen, inicia sesión y les deja al menos 3 partidas
// en el historial (para que /games, /home y el detalle devuelvan datos reales).
//
//   k6 run performance/k6/preparar.js        (desde la raíz del repositorio)
//
// Escribe performance/resultados/usuarios.json (tokens válidos 1 h; ignorado por Git). Va despacio a propósito:
// login y registro tienen un límite de 10 peticiones/s por IP en los reverse proxies.
import http from 'k6/http';
import { sleep } from 'k6';
import { MOVIL, CLAVE, USUARIOS, APERTURA, conBearer, leerJson } from './lib/comun.js';

export const options = {
  vus: 1,
  iterations: 1,
  setupTimeout: '10m',
};

function post(url, body, params) {
  return http.post(url, JSON.stringify(body), params || { headers: { 'Content-Type': 'application/json' } });
}

function iniciarSesion(usuario) {
  for (let intento = 0; intento < 5; intento += 1) {
    const r = post(`${MOVIL}/auth/login`, { username: usuario, password: CLAVE });
    if (r.status !== 429) return r;
    sleep(2); // límite de frecuencia: esperar y reintentar
  }
  return null;
}

function crearPartidaTerminada(token) {
  const p = conBearer(token);
  let r = post(`${MOVIL}/games`, { mode: 'local', timeControl: null }, p);
  if (r.status !== 201) return null;
  let estado = r.json();
  for (const uci of APERTURA) {
    r = post(`${MOVIL}/games/${estado.gameId}/moves`, { uci, expectedVersion: estado.version }, p);
    if (r.status !== 200) break;
    estado = r.json();
  }
  post(`${MOVIL}/games/${estado.gameId}/resign`, { side: 'white' }, p);
  return estado.gameId;
}

export function setup() {
  const usuarios = [];
  for (let i = 1; i <= USUARIOS; i += 1) {
    const nombre = `perf_${String(i).padStart(3, '0')}`;
    let r = iniciarSesion(nombre);
    if (r && r.status === 401) {
      post(`${MOVIL}/auth/register`, { username: nombre, password: CLAVE });
      sleep(0.2);
      r = iniciarSesion(nombre);
    }
    if (!r || r.status !== 200) {
      throw new Error(`no se pudo iniciar sesión con ${nombre}: ${r ? r.status : 'sin respuesta'}`);
    }
    const token = r.json('accessToken');
    const userId = r.json('user.userId');
    let partidas = (leerJson(http.get(`${MOVIL}/games?limit=20`, conBearer(token)), 'items') || [])
      .filter((g) => g.mode !== 'multiplayer')
      .map((g) => g.gameId);
    while (partidas.length < 3) {
      const id = crearPartidaTerminada(token);
      if (!id) break;
      partidas.push(id);
    }
    usuarios.push({ username: nombre, token, userId, partidas: partidas.slice(0, 10) });
    sleep(0.2); // ~5 logins/s: por debajo del límite de 10/s
  }
  return usuarios;
}

export default function () {}

export function handleSummary(data) {
  const usuarios = data.setup_data || [];
  console.log(`usuarios listos: ${usuarios.length}`);
  return { 'performance/resultados/usuarios.json': JSON.stringify(usuarios) };
}
