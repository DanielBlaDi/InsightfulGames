# Frontend web con Vike y Express

Rama `frontend-B`, 3 de noviembre de 2026. Referencia normativa: *Contrato técnico definitivo*,
secciones 4.4, 5 y 7.4.3. Este documento explica qué quedó hecho, cómo agregar páginas (Frontend A)
y qué tiene que cambiar en el despliegue (Infra).

## 1. Qué hay

Un solo proceso Node (Express 5 + Vike 0.4.268 + vike-react) sirve el frontend en el puerto 80.
Nginx, `index.html` y `game.html` ya no existen.

| Ruta | Qué hace | Dónde |
|---|---|---|
| `GET /health` | `200 {"status":"ok"}` | `server/index.js` |
| `/api/internal/*` | 404 antes de cualquier proxy. También bloquea `/API/Internal`, `/api//internal`, `/api/%69nternal` y `/api/x/../internal` | `server/routes.js` |
| `/api/ws/*` | Proxy WebSocket al gateway, sin `/api`, conservando `Origin` y `Cookie` | `server/index.js` |
| `/api/*` | Proxy REST al gateway, sin `/api`, conservando `Set-Cookie`, `Cookie`, `Idempotency-Key` e `Idempotency-Replayed`. Gateway caído: `503 SERVICES_UNAVAILABLE` | `server/index.js` |
| `/estadisticas` | **Renderizado en servidor**: el HTML ya trae los números. Sin sesión, 302 a `/login?next=%2Festadisticas` | `pages/estadisticas/` |
| `/` | La aplicación actual (`App.tsx`: portada, login y ajedrez), sin cambios, como aplicación de una sola página | `pages/index/` |
| `/login` | Provisional: monta `Login.tsx` sin cambios y vuelve a `next` tras iniciar sesión | `pages/login/` |
| `/dev/partida` | Simulador del módulo de juego (antes `game.html`). Solo existe con `npm run dev`; en producción da 404 y su código no está en el build | `pages/dev-partida/` |

El servidor no valida JWT ni guarda el token: eso lo hace el gateway.

## 2. Comandos

```bash
cd Frontend
npm ci
npm run dev                  # Vite + Vike en :5173, proxy /api a http://localhost:8080 (ws: true)
npm run build                # tsc -b && vite build -> dist/client y dist/server
API_GATEWAY_URL=http://localhost:8080 PORT=3000 npm start   # servidor de producción
npm test                     # requiere npm run build antes
npm run lint
```

`PORT` existe solo para ejecutar fuera de Docker (en Windows el puerto 80 suele pedir permisos). En
el contenedor no se define y el proceso escucha en 80.

## 3. Para Frontend A

### 3.1 Dónde van las páginas

Cada carpeta de `Frontend/pages/` es una ruta (enrutamiento por sistema de archivos de Vike):

```
pages/
  +config.ts          común: vike-react, ssr: false, idioma, título, <body>
  +Head.tsx           Tailwind CDN, su tema (tailwindConfig.ts) y fuentes
  index/+Page.tsx     "/"
  login/+Page.tsx     "/login"      (provisional: reemplázala)
  estadisticas/       "/estadisticas" (Frontend B: no tocar)
  jugar/+Page.tsx     "/jugar"           <- ejemplos de lo que falta
  historial/+Page.tsx "/historial"
  perfil/+Page.tsx    "/perfil"
  registro/+Page.tsx  "/registro"
  partida/@id/+Page.tsx  "/partida/{id}"   (parámetro: usePageContext().routeParams.id)
  unirse/@matchId/+Page.tsx "/unirse/{matchId}"
```

Una página de una sola página es solo un componente; no hace falta `+config.ts` porque `ssr: false`
ya es el valor común:

```tsx
// pages/historial/+Page.tsx
export default function Page() {
  return <Historial />; // el componente vive en src/, como hasta ahora
}
```

Título propio: `pages/historial/+config.ts` con `export default { title: 'Historial — Insightful Games' }`.

### 3.2 Navegación

Enlaces normales: `<a href="/historial">`. Vike los intercepta y navega sin recargar. Desde código:
`import { navigate } from 'vike/client/router'` y `navigate('/jugar')`.

Después de iniciar o cerrar sesión, conviene una recarga completa (`window.location.assign(url)`):
así cualquier página con renderizado en servidor ve la cookie nueva. Es lo que hace `pages/login`.

### 3.3 Sesión con cookie (sin `localStorage`)

- El JWT vive solo en la cookie `session` (HttpOnly). JavaScript no puede leerla y no debe guardarla.
- **¿Hay sesión?** `fetch('/api/stats/me')`: 200 = sí, 401 = no (contrato 5.4.4). No usar
  `/api/profile/me`: un 404 de perfil no significa sesión inválida.
- **Login**: `POST /api/auth/login` como hoy. El gateway responde el JSON **y** `Set-Cookie`. El
  `accessToken` del cuerpo se ignora; para mostrar el nombre se usa `user.username` de esa respuesta.
- **Logout**: `POST /api/auth/logout` (204, borra la cookie). Hoy `App.tsx` solo borra su estado.
- **401 o cierre WebSocket 4401**: ir a `/login?next=<ruta actual>`.
- **Por cambiar en lo existente** (tarea «Retiro del token del navegador»): `src/authSession.ts` y
  sus llamadas en `App.tsx` siguen guardando el token en `localStorage`. Hay que quitarlos y borrar
  las claves antiguas `accessToken` y `user`. No lo cambié porque es la migración de autenticación
  que les corresponde.

### 3.4 Ajedrez sin JWT

```tsx
import { PlayChess } from '../../src/game';

export default function Page() {
  return (
    <PlayChess
      onUnauthorized={() => window.location.assign('/login?next=/jugar')}
      onExit={() => window.location.assign('/')}
    />
  );
}
```

`token` ya no hace falta: el módulo usa `/api/*` y `/api/ws/*` con la cookie. La prop se acepta y se
ignora mientras `App.tsx` la siga pasando.

### 3.5 Reglas para no romper el renderizado en servidor

- `window`, `document` y `localStorage` solo en efectos o manejadores. Las páginas con `ssr: false`
  no corren en el servidor, pero `+Head.tsx` y `/estadisticas` sí.
- No activar `ssr: true` en otras páginas sin hablarlo: el contrato lo pide solo en `/estadisticas`.

### 3.6 Archivos que conviene no editar a la vez

| Archivo | Dueño |
|---|---|
| `server/*`, `vite.config.ts`, `Dockerfile`, `.dockerignore` | Frontend B |
| `pages/+config.ts`, `pages/+Head.tsx`, `pages/tailwindConfig.ts` | Compartidos: avisar antes de cambiarlos |
| `pages/estadisticas/*`, `src/stats/*`, `src/game/*` | Frontend B |
| `package.json`, `package-lock.json` | Compartidos: una sola persona instala a la vez |
| `src/App.tsx`, `src/components/*`, `src/authSession.ts`, `pages/index`, `pages/login` y las páginas nuevas | Frontend A |

## 4. Para Infra

Ya en el repositorio (rama `frontend-B`): `Frontend/Dockerfile` (con D mayúscula, como espera
`compose.yaml` en `containers`) y `Frontend/.dockerignore`. **No modifiqué `compose.yaml`.**

| Aspecto | Valor |
|---|---|
| Imagen | `node:22-alpine`, dos etapas: `npm ci` + `npm run build`; luego `npm ci --omit=dev` (unos 77 MB de `node_modules`) |
| Comando | `node server/index.js` (`NODE_ENV=production` ya está en la imagen) |
| Puerto | 80 dentro del contenedor; `FRONTEND_PORT` es el publicado |
| Usuario | `node`, sin root. Depende de que Docker permita puertos bajos a usuarios normales (por defecto desde Docker Engine 20.10). Si falla con `EACCES`, quitar `USER node` |
| Variable obligatoria | `API_GATEWAY_URL=http://api-gateway-component:8080`. Sin ella el proceso termina al arrancar |
| Healthcheck | Ya en el Dockerfile: `wget -q --spider http://127.0.0.1/health` |
| Nginx | Eliminado; no hace falta montar plantillas ni `envsubst` |

Cambios en el bloque `frontend` de `compose.yaml` (rama `containers`):

1. Quitar `profiles: ["pendiente"]` para que arranque con el resto.
2. `depends_on: api-gateway-component: condition: service_healthy`.
3. En el gateway web, `WS_ALLOWED_ORIGINS` debe ser el origen del navegador: `http://localhost` si
   `FRONTEND_PORT=80`, o `http://localhost:<FRONTEND_PORT>` si no. El proxy no cambia `Origin`.
4. `COOKIE_SECURE=false` en local; `true` solo detrás de HTTPS.

## 5. Pruebas ejecutadas (3 de noviembre, Windows, Node 20.19.5)

| Prueba | Resultado |
|---|---|
| `npm run build` (incluye `tsc -b`) y `npm run lint` | Sin errores ni avisos |
| `npm test`: 15 casos contra un gateway simulado | 15/15 |
| La misma suite sobre una copia con solo `npm ci --omit=dev`, sin código fuente | 15/15 |
| `npm run dev`: `/`, 302 de `/estadisticas`, aviso con gateway caído, 404 de `/api/internal`, `/dev/partida` | Correcto |
| Chrome real → Vike → **gateway real de `containers`** → Auth, Profile/Stats y Single Player simulados | 14/14 |

El recorrido en Chrome comprobó: 302 sin sesión; login por `Login.tsx` y vuelta a `/estadisticas`;
estadísticas en pantalla; cookie HttpOnly y SameSite=Lax invisible para `document.cookie`;
`localStorage` vacío; hidratación de React sobre el HTML del servidor; datos presentes con
JavaScript desactivado; `/api/internal/*` en 404; WebSocket de ida y vuelta hasta Single Player con
el usuario del JWT; cierre 4403 desde un origen no permitido; logout y nuevo 302; `/` sigue
cargando; consola sin errores. El script está fuera del repositorio porque usa puppeteer-core.

**Sin probar:** imagen Docker (no hay Docker), Node 22 (local es 20.19.5), Compose, HTTPS y
`COOKIE_SECURE=true`, servicios reales de Auth, Profile/Stats y Single Player, y una partida de
ajedrez completa por la nueva cadena (Single Player aún no usa el protocolo del contrato).

## 6. Ambigüedades y decisiones

1. **`next` codificado.** El contrato escribe `/login?next=/estadisticas`; `loadStatsPage` envía
   `/login?next=%2Festadisticas`. Es la misma URL al decodificarla; no lo cambié.
2. **Estado vacío con ceros.** El contrato pide estado vacío y la tarea pide mostrar los ceros reales:
   `StatsView` muestra ambos.
3. **Simulador.** El contrato retira `game.html` y pide conservar el simulador en desarrollo, sin
   decir dónde. Queda en `/dev/partida`, solo en desarrollo.
4. **`/login` provisional.** El 302 necesita un destino y `/login` no existía. Reutiliza `Login.tsx`
   sin cambios y no guarda el token. Frontend A la reemplaza.
5. **`/partida/{id}`** (ya señalado en el contrato, 24.3): no se define cómo se conoce `mode` al abrir
   la URL directamente.
