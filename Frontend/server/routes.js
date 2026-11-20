import { posix } from 'node:path';

// Reglas de ruta compartidas por el servidor de producción (server/index.js) y el proxy de
// desarrollo (vite.config.ts). Contrato técnico definitivo, 5.4.1.

/**
 * Ruta normalizada como la vería el gateway: sin query, decodificada, sin barras repetidas ni
 * segmentos "." y "..", en minúsculas. Devuelve null si no se puede decodificar.
 * @param {string} url
 * @returns {string | null}
 */
function normalizedPath(url) {
  const path = url.split('?')[0];
  try {
    return posix.normalize(decodeURIComponent(path)).replace(/\/{2,}/g, '/').toLowerCase();
  } catch {
    return null;
  }
}

/**
 * /api/internal/* nunca llega al gateway (4.4 y 5.4.1). Se compara la ruta normalizada para que
 * variantes como /API/Internal, /api//internal o /api/%69nternal tampoco pasen. Una ruta mal
 * codificada se trata como interna: se bloquea.
 * @param {string} url
 */
export function isInternalApiPath(url) {
  const path = normalizedPath(url);
  return path === null || path === '/api/internal' || path.startsWith('/api/internal/');
}

/** @param {string} url */
export function isSocketApiPath(url) {
  return url.startsWith('/api/ws/');
}
