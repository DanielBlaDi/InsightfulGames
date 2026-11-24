// Configuración y utilidades comunes de las pruebas de rendimiento (k6).
//
// Las pruebas entran por las mismas puertas que los usuarios reales: los WAF por HTTPS
// (web https://localhost:8443, app https://localhost:8444). El certificado se valida contra el
// almacén de Windows (CA de mkcert instalada con `mkcert -install`); nunca se desactiva la verificación.
import { sleep } from 'k6';

export const WEB = __ENV.WEB_URL || 'https://localhost:8443';
export const MOVIL = __ENV.MOVIL_URL || 'https://localhost:8444';
export const ORIGEN = __ENV.WEB_ORIGIN || WEB; // debe estar en WS_ALLOWED_ORIGINS del gateway web
export const WS_WEB = WEB.replace(/^http/, 'ws');
export const CLAVE = __ENV.CLAVE_USUARIOS || 'Rendimiento-2026!';
export const USUARIOS = Number(__ENV.USUARIOS || 50);

// Pausa de "persona real" entre acciones (think time)
export function pausa(min = 1, max = 3) {
  sleep(min + Math.random() * (max - min));
}

export function conBearer(token, tags) {
  return { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, tags };
}

// La web usa la cookie de sesión (el mismo JWT que emite Auth)
export function conCookie(token, tags) {
  return { headers: { Cookie: `session=${token}`, 'Content-Type': 'application/json' }, tags };
}

export function leerJson(res, ruta) {
  try {
    return res.json(ruta);
  } catch (e) {
    return undefined;
  }
}

// Apertura fija y siempre legal para las partidas locales
export const APERTURA = ['e2e4', 'e7e5', 'g1f3', 'b8c6'];

// Pieza en una casilla según la FEN ("e2" -> 'P'); null si está vacía
export function piezaEn(fen, casilla) {
  const filas = (fen || '').split(' ')[0].split('/');
  const fila = filas[8 - Number(casilla[1])] || '';
  let columna = 0;
  const objetivo = casilla.charCodeAt(0) - 97;
  for (const c of fila) {
    if (c >= '1' && c <= '8') {
      columna += Number(c);
    } else {
      if (columna === objetivo) return c;
      columna += 1;
    }
  }
  return null;
}

// Jugada legal al azar a partir de legalMoves del GameState (corona a dama si hace falta)
export function jugadaAleatoria(estado) {
  const legales = estado.legalMoves || {};
  const origenes = Object.keys(legales).filter((k) => legales[k] && legales[k].length);
  if (!origenes.length) return null;
  const desde = origenes[Math.floor(Math.random() * origenes.length)];
  const destinos = legales[desde];
  const hasta = destinos[Math.floor(Math.random() * destinos.length)];
  const pieza = piezaEn(estado.fen, desde);
  const corona = (pieza === 'P' && hasta[1] === '8') || (pieza === 'p' && hasta[1] === '1');
  return desde + hasta + (corona ? 'q' : '');
}

// Etapas de un ramping-vus escaladas por un factor (para repartir VUs entre escenarios)
export function escalar(etapas, factor) {
  return etapas.map((e) => ({ duration: e.duration, target: Math.max(e.target ? 1 : 0, Math.round(e.target * factor)) }));
}
