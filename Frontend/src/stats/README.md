# Estadísticas (`/estadisticas`)

Piezas de la página de estadísticas del contrato v9 (sección 6), preparadas para el SSR con Vike.

**Estado: todavía no hay SSR.** El frontend aún no usa Vike (lo prepara Frontend A). Estos
archivos no están montados en ninguna página; cuando Vike exista se conectan así:

| Archivo | Uso |
|---|---|
| `loadStatsPage.ts` | Se ejecuta en el servidor. Pide `GET /stats/me` al gateway web (`API_GATEWAY_URL`) con la cookie que llegó del navegador. Devuelve `ok`, `unavailable` o `unauthenticated` (con `redirectTo: /login?next=%2Festadisticas`). |
| `StatsView.tsx` | Componente puro, sin estado ni efectos: se renderiza en el servidor con los datos anteriores. |
| `types.ts` | `PlayerStats` (respuesta de `/stats/me`) y `StatsPageData`. |

Esquema previsto con Vike (a coordinar con Frontend A):

```ts
// pages/estadisticas/+data.ts (se ejecuta solo en el servidor)
export async function data(pageContext) {
  const result = await loadStatsPage({
    gatewayUrl: process.env.API_GATEWAY_URL!,
    cookie: pageContext.headers?.cookie,
  });
  if (result.kind === 'unauthenticated') throw redirect(result.redirectTo); // 302
  return result;
}
// pages/estadisticas/+Page.tsx
export default () => <StatsView data={useData()} />;
```

Pendiente de otros componentes: el gateway web debe publicar `GET /stats/me` hacia Profile/Stats
y aceptar la cookie `session`.
