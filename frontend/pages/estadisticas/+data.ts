import { redirect } from 'vike/abort';
import type { PageContextServer } from 'vike/types';
import { loadStatsPage } from '../../src/stats/loadStatsPage';

export type Data = Awaited<ReturnType<typeof data>>;

// Se ejecuta solo en el servidor (5.4.3): reenvía la cookie del navegador a GET /stats/me del
// gateway web. Sin cookie o con 401 responde 302 al login; si el gateway falla, la página se
// renderiza con el aviso "no disponible".
export async function data(pageContext: PageContextServer) {
  const result = await loadStatsPage({
    gatewayUrl: process.env.API_GATEWAY_URL ?? 'http://localhost:8080',
    cookie: pageContext.headers?.cookie,
  });
  if (result.kind === 'unauthenticated') {
    throw redirect(result.redirectTo);
  }
  return result;
}
