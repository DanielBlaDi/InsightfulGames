/**
 * Rutas públicas del frontend (contrato v9, sección 6). El navegador habla solo con su propio
 * servidor: REST en /api/* y WebSocket en /api/ws/*, que ese servidor reenvía al gateway web.
 * La sesión viaja sola en la cookie session; el código nunca toca el token.
 *
 * Solo se llaman desde efectos o manejadores de eventos, nunca al renderizar: así el módulo se
 * puede renderizar en el servidor sin acceder a window.
 */
export function apiUrl(path: string): string {
  return `/api${path}`;
}

export function apiSocketUrl(path: string): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}/api${path}`;
}
