# Estadísticas (`/estadisticas`)

Única página con renderizado en servidor (contrato técnico definitivo, 5.4.3). Se monta en
`pages/estadisticas/`:

| Archivo | Uso |
|---|---|
| `pages/estadisticas/+config.ts` | `ssr: true` y título. |
| `pages/estadisticas/+data.ts` | Solo en el servidor: llama a `loadStatsPage` con `API_GATEWAY_URL` y la cookie de la petición; si no hay sesión lanza `redirect()` (302). |
| `pages/estadisticas/+Page.tsx` | Pinta `StatsView` con los datos; el navegador lo hidrata. |
| `loadStatsPage.ts` | Pide `GET /stats/me` al gateway web con la cookie del navegador. Devuelve `ok`, `unavailable` o `unauthenticated` (con `redirectTo: /login?next=%2Festadisticas`). |
| `StatsView.tsx` | Componente puro, sin estado ni efectos. Con 0 partidas muestra los ceros y el estado vacío; si el gateway falla, el aviso «no disponible». |
| `types.ts` | `PlayerStats` (respuesta de `/stats/me`) y `StatsPageData`. |

Pruebas: `server/server.test.js` (`npm run build && npm test`).
