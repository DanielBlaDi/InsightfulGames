# Frontend web con Vike y Express

Rama de integración: `frontend-B-vike`, basada en `containers` (3 de noviembre de 2026).
Referencia normativa: *Contrato técnico definitivo*,
secciones 4.4, 5 y 7.4.3. Este documento explica qué quedó hecho, cómo agregar páginas (Frontend A)
y qué tiene que cambiar en el despliegue.

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
| `/` | La aplicación actual (`App.tsx`: portada, login y ajedrez) como aplicación de una sola página. Sesión por cookie y menú de la cuenta en el ícono de usuario (Mi perfil, Estadísticas, Cerrar sesión) | `pages/index/` |
| `/perfil` | Aplicación de una sola página: pide `GET /api/profile/me` en el navegador. 401 → `/login?next=%2Fperfil`; 404 → "perfil todavía no disponible" (la sesión sigue); 503 → aviso con reintento | `pages/perfil/`, `src/profile/` |
| `/login` | Provisional: monta `Login.tsx` y vuelve a `next` (solo rutas del propio sitio) tras iniciar sesión | `pages/login/` |
| `/dev/partida` | Simulador del módulo de juego (antes `game.html`). Solo existe con `npm run dev`; en producción da 404 y su código no está en el build | `pages/dev-partida/` |

El servidor no valida JWT ni guarda el token: eso lo hace el gateway.

## 2. Comandos

```bash
cd Frontend
npm ci
npm run dev                  # Vite + Vike en :5173, proxy /api a http://localhost:8080 (ws: true)
npm run build                # tsc -b && vite build -> dist/client y dist/server
API_GATEWAY_URL=http://localhost:8080 PORT=3000 npm start   # servidor de producción
npm test                     # servidor (requiere npm run build antes) y src/auth/session.ts
npm run lint
```

`PORT` existe solo para ejecutar fuera de Docker (en Windows el puerto 80 suele pedir permisos). En
el contenedor no se define y el proceso escucha en 80.

## 3. Para Frontend A

### 3.0 Pasos, en orden

1. Partir de `frontend-B-vike` (`git switch -c <tu-rama> origin/frontend-B-vike`), `npm ci` y
   `npm run dev`. Vike y el proxy ya funcionan; no hace falta tocar `server/` ni `vite.config.ts`.
2. Crear cada pantalla como página en `Frontend/pages/<ruta>/+Page.tsx` (3.1), reutilizando los
   componentes de `src/`.
3. Navegar con enlaces `<a href>` o `navigate()` en vez del estado `view` de `App.tsx` (3.2).
4. ~~Quitar `localStorage` y pasar a la sesión por cookie (3.3).~~ Hecho el 3 de noviembre (`src/auth/session.ts`).
5. Montar el ajedrez sin token en `/jugar` (3.4).
6. Reemplazar la `/login` provisional por la definitiva, conservando el parámetro `next`.
7. Antes de cada commit: `npm run build && npm run lint && npm test`.

### 3.1 Dónde van las páginas

Cada carpeta de `Frontend/pages/` es una ruta (enrutamiento por sistema de archivos de Vike):

```
pages/
  +config.ts          común: vike-react, ssr: false, idioma, título, <body>
  +Head.tsx           Tailwind CDN, su tema (tailwindConfig.ts) y fuentes
  index/+Page.tsx     "/"
  login/+Page.tsx     "/login"      (provisional: reemplázala)
  estadisticas/       "/estadisticas" (Frontend B: no tocar)
  perfil/             "/perfil"       (hecho: src/profile/ProfilePage.tsx)
  jugar/+Page.tsx     "/jugar"           <- ejemplos de lo que falta
  historial/+Page.tsx "/historial"
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
- **Implementado** (3 de noviembre) en `src/auth/session.ts`, `App.tsx` y `Landing.tsx`:
  `src/authSession.ts` ya no existe; al cargar se borran las claves antiguas `accessToken` y `user`;
  el estado de React guarda solo el nombre; la sonda es `readSession()` (stats para la sesión y
  perfil para el nombre: un 404 o 503 del perfil no cierra la sesión); salir llama a
  `POST /api/auth/logout`. Verificado en Chrome: `localStorage` y `sessionStorage` vacíos y
  `document.cookie` sin `session`.

```ts
// Sonda de sesión (contrato 5.4.4). Solo en efectos o manejadores, nunca al renderizar.
async function hasSession(): Promise<boolean | 'unavailable'> {
  const res = await fetch('/api/stats/me', { credentials: 'same-origin' });
  if (res.status === 200) return true;
  if (res.status === 401) return false;
  return 'unavailable'; // 503 u otros: mostrar reintento, no mandar al login
}
```

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

## 4. Front A

Ya en la rama `frontend-B-vike`: `Frontend/Dockerfile` (con D mayúscula, como espera
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

Cambios en `compose.yaml` y `.env.example` (revisados sobre `containers`, commit `89c0d8e`):

1. **Primero, un healthcheck en `api-gateway-component`.** Hoy no tiene. Con
   `condition: service_healthy` sin healthcheck, el frontend nunca arrancaría. El gateway ya
   responde `GET /health` y su imagen (`python:3.10-slim`) tiene Python:

   ```yaml
   api-gateway-component:
     healthcheck:
       test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]
       interval: 10s
       timeout: 5s
       retries: 5
       start_period: 10s
   ```

2. **Después**, en `frontend`:
   - quitar `profiles: ["pendiente"]` para que arranque con el resto;
   - añadir `depends_on: { api-gateway-component: { condition: service_healthy } }`;
   - cambiar `${FRONTEND_PORT}` por `${FRONTEND_PORT:?}`, como el gateway móvil: vacío hace fallar
     Compose.
3. **`.env.example`**: declarar las variables que Compose ya exige con `:?` y hoy faltan:
   `WS_ALLOWED_ORIGINS`, `COOKIE_SECURE`, `HTTP_TIMEOUT` y `LOG_LEVEL`. Valores locales:
   - `FRONTEND_PORT=80`;
   - `WS_ALLOWED_ORIGINS=http://localhost` (con otro puerto: `http://localhost:<FRONTEND_PORT>`;
     el proxy no cambia `Origin`);
   - `COOKIE_SECURE=false` (`true` solo detrás de HTTPS);
   - `HTTP_TIMEOUT=15` y `LOG_LEVEL=INFO`.
4. **Restos que el contrato manda retirar en el gateway** (no bloquean al frontend):
   - `CORS_ORIGINS`;
   - el puerto publicado `127.0.0.1:8080`, que va a `compose.override.yaml`;
   - las rutas públicas `/engine/*`: hoy Vike las reenvía como `/api/engine/*`.

Comprobación sugerida sin Compose: `docker build -t frontend:dev Frontend` y
`docker run --rm -e API_GATEWAY_URL=http://host.docker.internal:8080 -p 8000:80 frontend:dev`;
`http://localhost:8000/health` debe responder `{"status":"ok"}`.

## 5. Pruebas ejecutadas (3 de noviembre, Windows, Node 20.19.5)

| Prueba | Resultado |
|---|---|
| `npm run build` (incluye `tsc -b`) y `npm run lint` | Sin errores ni avisos |
| `npm test`: 15 casos contra un gateway simulado | 15/15 |
| La misma suite sobre una copia con solo `npm ci --omit=dev`, sin código fuente | 15/15 |
| `npm run dev`: `/`, 302 de `/estadisticas`, aviso con gateway caído, 404 de `/api/internal`, `/dev/partida` | Correcto |
| Chrome real → Vike → **gateway real de `containers`** → Auth, Profile/Stats y Single Player simulados | 14/14 |
| Repetido en `frontend-B-vike` (`npm ci` limpio, build, lint, `npm test` y Chrome con el `main.py` de la rama) | 15/15 y 14/14 |

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
