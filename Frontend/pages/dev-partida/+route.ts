import type { PageContext } from 'vike/types';

// Simulador del módulo de partida (antes /game.html), solo con `npm run dev`. En el build de
// producción la ruta no existe (404) y el código del simulador no se incluye (5.3).
export default (pageContext: PageContext) => import.meta.env.DEV && pageContext.urlPathname === '/dev/partida';
