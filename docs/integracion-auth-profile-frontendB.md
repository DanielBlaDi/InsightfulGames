# Integración de Auth, Profile/Stats y Frontend B (Prototipo 2, contrato v9)

Rama: `frontend-B`. Estado al 1 de noviembre. Entrega: 3 de noviembre.

Este documento dice qué está listo en estos tres componentes, qué tiene que hacer cada equipo para
conectarlos y qué decisiones del contrato necesitan acuerdo. **Nada de lo descrito se ha probado
con servicios reales** (PostgreSQL, MySQL, RabbitMQ, gateway, Single Player): las pruebas usan H2,
mocks y un navegador simulado.

## 1. Qué está listo

| Componente | Estado | Pruebas ejecutadas |
|---|---|---|
| Profile/Stats (`Backend/profile-stats-component`) | Rutas internas de perfil, stats y borrado; consumo de `user.registered` y `game.finished` con idempotencia, reintentos y `.dlq` | 21 (H2 modo PostgreSQL) |
| Auth (`Backend/auth-component`) | Rutas `/internal/auth/*`, errores con formato común, outbox de `user.registered`, borrado coordinado | 21 (H2 modo MySQL) |
| Frontend B (`Frontend/src/game`) | REST `/api/games` y WebSocket `/api/ws/games/{id}` con cookie, `GameState` v9, `expectedVersion` | build, lint y 22 comprobaciones en DOM simulado |
| Estadísticas (`Frontend/src/stats`) | Vista y cargador de servidor para `/estadisticas`; **sin SSR hasta que exista Vike** | 9 comprobaciones en Node |

## 2. Infra (`compose.yaml`, `.env.example`)

1. **RabbitMQ** (sección 22): imagen `rabbitmq:3.13-management`, sin plugins, `expose: 5672`,
   consola 15672 solo en `compose.override.yaml`. Healthcheck: `rabbitmq-diagnostics -q ping`.
   Volumen `rabbitmq-data`. Variables `RABBITMQ_DEFAULT_USER` y `RABBITMQ_DEFAULT_PASS`.
2. **PostgreSQL de Profile/Stats**: servicio `postgres-profile` (contenedor `postgres-profile-db`),
   montando `./Databases/profile/01-init.sql` en `/docker-entrypoint-initdb.d/` como `:ro`.
   Healthcheck con `pg_isready`. Volumen `postgres-data`.
3. **Profile/Stats**: contexto `./Backend/profile-stats-component`, `expose: 8087`, variables
   `SERVER_PORT=8087`, `POSTGRES_URL=jdbc:postgresql://postgres-profile:5432/${POSTGRES_DB}`,
   `POSTGRES_USER`, `POSTGRES_PASSWORD`, `RABBITMQ_URL=amqp://user:pass@rabbitmq:5672`.
   `depends_on` PostgreSQL y RabbitMQ con `service_healthy`. Bloque completo en
   `Backend/profile-stats-component/README.md`.
4. **Auth**: añadir `RABBITMQ_URL`, `GATEWAY_INTERNAL_URL=http://api-gateway-component:8080` y
   `depends_on: rabbitmq (service_healthy)`. El usuario de MySQL necesita permiso `CREATE` en su
   base (lo tiene si es `MYSQL_USER`): Auth crea `outbox_events` al arrancar.
5. **`.env.example`**: añadir `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
   `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`, `PROFILE_STATS_PORT=8087`; cambiar
   `BOTSITO_PORT` por `BOTCITO_PORT` (Compose ya usa el segundo); declarar `JWT_SECRET` como
   obligatoria (`${JWT_SECRET:?}`).
6. **Mayúsculas en rutas** (sección 22): `./frontend`, `dockerfile: Dockerfile` y `./databases` no
   coinciden con `Frontend/`, `dockerfile` y `Databases/`. Falla en Linux.
7. **Orden de arranque**: bases y RabbitMQ → Auth, Game Logic, Profile/Stats → resto. Si Auth
   publica antes de que Profile/Stats declare su cola, el evento espera en el outbox (no se pierde).

## 3. Gateway web (`Backend/api-gateway/main.py`)

1. **Login con cookie** (sección 4): `POST /auth/login` responde el JSON y además
   `Set-Cookie: session=<jwt>; HttpOnly; SameSite=Lax; Path=/; Max-Age=3600` (`Secure` con HTTPS).
   `POST /auth/logout` responde 204 con `session=; Max-Age=0`, sin llamar a Auth.
2. **Validar el JWT desde la cookie o desde `Authorization`**, quitar cualquier `X-User-Id` del
   cliente y poner el suyo.
3. **WebSocket** `WS /ws/games/{id}`: token desde la cookie (ya no `?token=`) y Origin contra
   `WS_ALLOWED_ORIGINS`; cierre 4403 si el Origin no está permitido. Hoy lee `?token=`.
4. **Rutas nuevas**: `GET /profile/me` → `GET /internal/profile/users/{sub}/profile` y
   `GET /stats/me` → `GET /internal/profile/users/{sub}/stats`. `DELETE /auth/account` →
   `DELETE /internal/auth/account` y, si responde 204, borrar la cookie.
5. **Auth por rutas internas**: llamar a `/internal/auth/register` y `/internal/auth/login`
   (Auth mantiene `/auth/*` como alias mientras tanto).
6. **Passthrough `/internal/*`** (sección 4): sin él, el borrado de cuenta de Auth no llega a Game
   Logic, Tutor ni Profile/Stats y siempre responde 503.

## 4. Frontend A (Vike, cookies y `/estadisticas`)

1. **Servidor Vike** en el puerto 80 (sección 6): estáticos, proxy `/api/*` → gateway quitando
   `/api` y reenviando `Set-Cookie`; proxy WebSocket `/api/ws/*` con `Upgrade`, `Connection` y
   `Origin`; 404 a `/api/internal/*` antes de cualquier proxy.
2. **`/estadisticas` con SSR**: `+data.ts` llama a `loadStatsPage({ gatewayUrl: API_GATEWAY_URL,
   cookie })` de `src/stats/loadStatsPage.ts`; si devuelve `unauthenticated`, 302 a
   `/login?next=/estadisticas`; `+Page.tsx` pinta `<StatsView data={...} />`. Ejemplo en
   `Frontend/src/stats/README.md`.
3. **Quitar `localStorage`** de `App.tsx` y `Login.tsx` (y `src/authSession.ts`): la sesión vive
   solo en la cookie. Para saber si hay sesión al cargar, una petición a `/api/profile/me`
   (200 = con sesión, 401 = sin sesión). Cerrar sesión = `POST /api/auth/logout`.
4. **Montar el ajedrez sin token**: `<PlayChess onUnauthorized={irAlLogin} onExit={irAlInicio} />`.
   La prop `token` sigue aceptándose e ignorándose para no romper el `App.tsx` actual.
5. **Desarrollo con `npm run dev`**: el proxy de `vite.config.ts` necesita `ws: true` para `/api/ws`.

## 5. Otros componentes de los que dependemos

| Componente | Qué falta | Afecta a |
|---|---|---|
| Game Logic (rama `GameLogic`) | Publicar `game.finished` (exchange `game.events`, clave `game.finished`, campos de la sección 17); `DELETE /internal/logic/users/{userId}`; `color` en cada jugada de `moves`; `expectedVersion` en `/moves` y `VERSION_CONFLICT` | Stats (sin eventos siempre son 0), borrado de cuenta, Frontend B |
| Tutor | `DELETE /internal/tutor/users/{userId}` (204 aunque no haya datos) | Borrado de cuenta |
| Single Player | Protocolo de la sección 9: cookie, `expectedVersion`, `GameState` v9, rutas `/internal/single-player/*` | Frontend B |
| Multiplayer | Partidas multiplayer y su `game.finished` | Stats: solo cuentan partidas multiplayer |
| Gateway móvil (rama `mobile`) | Compatible: usa `/internal/auth/*` y `/internal/profile/users/{id}/*`. Un perfil inexistente (404) aparece como "No disponible" en `/home` | — |

## 6. Decisiones del contrato

**Internas, seguras (no cambian ninguna interfaz):**

- Tabla `deleted_users` en Profile/Stats, para no recrear perfiles borrados.
- Tabla `outbox_events` en la base de Auth.
- Colas de espera `<cola>.wait` para los reintentos (v9 define la espera, no el nombre).
- Profile/Stats acepta `SERVER_PORT` y `PORT`.
- `/stats` devuelve ceros si no hay perfil, sin crear filas.

**Requieren acuerdo del equipo:**

1. **Perfil inexistente**: v9 pide crearlo al leerlo, pero la ruta no trae el `username`. Hoy
   responde 404 `PROFILE_NOT_FOUND`, un código que no está en la sección 20. Opciones: aceptar el
   404 y añadir el código, o que el gateway envíe el `username` del JWT.
2. **Esquema MySQL de Auth**: v9 dice `id` y `created_at`; el script real usa `user_id` sin fecha.
   Cambiarlo obliga a recrear el volumen. Propuesta: corregir el contrato.
3. **Mensaje `error` en el WebSocket de Single Player**: GameService lo envía (Botcito o Game Logic
   caídos) y Frontend B lo muestra, pero la sección 9 no lo lista (sí está en Multiplayer).
4. **`POSTGRES_URL`**: la sección 21 pide `*_URL` con `http://`; Spring necesita
   `jdbc:postgresql://...`.
5. **Declaraciones de RabbitMQ**: todos los servicios deben declarar `user.events` y `game.events`
   como `topic` durables y `retry.events` como `direct` durable; si un servicio usa otros
   argumentos, RabbitMQ rechaza la declaración.
6. **Rutas `/auth/*` de Auth**: alias temporales; quitarlos cuando el gateway use `/internal/auth/*`.

## 7. Verificación cuando haya Docker

1. `docker compose up -d --build` y `docker compose ps`: todos `healthy`.
2. Registrar un usuario por el gateway; en RabbitMQ (`rabbitmqctl list_queues`) la cola
   `profile.user-registered` queda en 0 y `GET /api/profile/me` responde el perfil.
3. Parar RabbitMQ, registrar otro usuario (201), arrancarlo: el perfil aparece en segundos.
4. Publicar un `game.finished` multiplayer a mano en `game.events` y comprobar `/api/stats/me`.
5. `DELETE /api/auth/account` con Tutor parado: 503 y el usuario sigue existiendo; con todo
   arriba: 204, la cookie se borra y `/api/profile/me` responde 404.
6. Jugar una partida local y una contra Botcito desde `/jugar` con la cookie de sesión.
