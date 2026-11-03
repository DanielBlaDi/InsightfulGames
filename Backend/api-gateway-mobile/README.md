# API Gateway móvil

Contrato técnico definitivo (secciones 4.11 y 5). FastAPI, puerto 8090. Solo habla con el gateway interno (`GATEWAY_INTERNAL_URL`,
que en el compose es `api-gateway-component`, rutas `/internal/*`). Ya está en el `compose.yaml` raíz.

**Lista de partidas.** El contrato (4.1) define `GET /internal/logic/games` → `{items, nextCursor}` y Game Logic ya lo cumple
(GL-04). El gateway deja pasar esa respuesta sin transformarla: el cursor es opaco y la paginación la hace Game Logic.
Una lista plana o el formato anterior `{matches, cursor}` ya no se convierten; se responden como 502 `UPSTREAM_ERROR`.

| Ruta pública (app)        | Auth | Interna                                                            |
| ------------------------- | ---- | ------------------------------------------------------------------ |
| `POST /auth/register`     | no   | `POST /internal/auth/register`                                     |
| `POST /auth/login`        | no   | `POST /internal/auth/login`                                        |
| `GET /home`               | sí   | agrega profile + stats + `logic/games?limit=5`                     |
| `GET /profile/me`         | sí   | `GET /internal/profile/users/{userId}/profile`                     |
| `GET /stats/me`           | sí   | `GET /internal/profile/users/{userId}/stats`                       |
| `GET /games?limit&cursor` | sí   | `GET /internal/logic/games?userId=&limit=&cursor=` (limit máx. 20) |
| `GET /games/{id}`         | sí   | `GET /internal/single-player/games/{id}` (local, vs_bot)           |
| `GET /matches/{id}`       | sí   | `GET /internal/multiplayer/matches/{id}` (multiplayer)             |

- `userId` sale del claim `sub` del JWT (solo HS256, debe ser UUID; HS384/HS512 se rechazan). El cliente nunca lo envía.
- Descarta cualquier `X-User-Id` del cliente; solo lo pone en los dos detalles (Single Player / Multiplayer lo necesitan).
- `/internal/*` desde fuera → 404. Sin cookies, sin Tutor, sin borrado de cuenta.
- `/home`: cada sección es independiente (`null` + nombre en `unavailable`); 503 `SERVICES_UNAVAILABLE`
  solo si no se llega al gateway interno. `recentGames` es el `items` de la lista (5 más recientes).
- Errores traducidos según el servicio de origen (`GAME_NOT_FOUND` / `MATCH_NOT_FOUND` / `INVALID_CREDENTIALS` / `USERNAME_TAKEN`).
- Solo emite códigos del catálogo 4.12. Un método no soportado responde 404 `NOT_FOUND`; un 409 o 422 de un servicio sin formato de error común responde 502 `UPSTREAM_ERROR`.
- Un id de ruta que no es UUID responde 404 sin llegar al gateway interno.
- No arranca sin `JWT_SECRET`.

## Variables

`PORT=8090`, `GATEWAY_INTERNAL_URL`, `JWT_SECRET` (obligatoria), `JWT_ALGORITHM=HS256` (otro valor impide el arranque), `HTTP_TIMEOUT=15`, `LOG_LEVEL`.

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest -q     # unitarias + cadena mixta sin red; las e2e se omiten si no defines MOBILE_GATEWAY_URL
```

| Archivo                       | Qué prueba                                                                                                                           | Necesita             |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | -------------------- |
| `tests/test_gateway.py`       | El gateway móvil contra un gateway interno simulado con `httpx.MockTransport`                                                        | nada                 |
| `tests/test_mixed_harness.py` | Cadena gateway móvil → gateway interno mixto → servicios "reales" imitados con las respuestas que hoy dan Auth, Profile y Game Logic | nada                 |
| `tests/test_e2e_mixed.py`     | Registro, login, perfil, estadísticas, inicio, historial paginado y detalle contra **procesos reales**                               | `MOBILE_GATEWAY_URL` |

## Probar con lo que ya sirve y simular lo que falta

El gateway web real aún no tiene el passthrough `/internal/*` (GW-04), así que el gateway móvil no puede llegar a los
servicios por el camino de producción. `tools/mixed_internal_gateway.py` ocupa ese lugar: cada ruta `/internal/*` va al
servicio **real** si defines su URL, y si no, a la simulación (`tools/fake_internal_gateway.py`).

| Servicio      | Estado hoy                                                           | Cómo se prueba                                                                           |
| ------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Auth          | real, `/internal/auth/*`                                             | `AUTH_URL=http://localhost:8081`                                                         |
| Profile/Stats | real, `/internal/profile/*`                                          | `PROFILE_URL=http://localhost:8087`                                                      |
| Game Logic    | real, `/internal/logic/*`, lista `{items, nextCursor}` (GL-04 hecho) | `LOGIC_URL=http://localhost:8082`                                                        |
| Single Player | **no sirve**: llama a `/logic/*`, que ya no existe                   | `SINGLE_PLAYER_MODE=via-logic` lee la partida real de Game Logic y aplica la visibilidad |
| Multiplayer   | no existe                                                            | simulado, o `MULTIPLAYER_MODE=via-logic` (lee `by-match` de Game Logic)                  |

`LOGIC_ADAPT=1` solo sirve para un Game Logic antiguo que aún responda `{matches, cursor}`; por omisión está apagado y la lista real pasa sin tocar.

**1. Servicios reales** (opcional; sin esto todo queda simulado). Desde la raíz del repo, con `.env` completo:

```bash
docker compose -f compose.yaml -f Backend/api-gateway-mobile/tools/compose.mixed.yaml up -d --build \
  mysql postgres-profile rabbitmq mongo auth-component profile-stats-component game-logic-component
```

`compose.mixed.yaml` publica Auth (8081), Game Logic (8082) y Profile/Stats (8087) solo en 127.0.0.1 (requiere Docker
Compose 2.24 o más nuevo por `!override`). Comprueba con `curl localhost:8081/health`, `:8082/health`, `:8087/health`.

**2. Gateway interno mixto** (puerto 8080). Quita de la línea lo que NO esté levantado:

```bash
cd Backend/api-gateway-mobile
export JWT_SECRET=<el mismo de tu .env, 32 bytes o más>
AUTH_URL=http://localhost:8081 PROFILE_URL=http://localhost:8087 LOGIC_URL=http://localhost:8082 \
  uvicorn --app-dir tools mixed_internal_gateway:app --port 8080
curl localhost:8080/health      # muestra qué es real y qué es simulado
```

**3. Gateway móvil** (puerto 8090) apuntando al mixto:

```bash
GATEWAY_INTERNAL_URL=http://localhost:8080 uvicorn main:app --port 8090
```

**4. Pruebas de punta a punta**:

```bash
MOBILE_GATEWAY_URL=http://localhost:8090 \
LOGIC_URL=http://localhost:8082 PROFILE_URL=http://localhost:8087 \
  pytest tests/test_e2e_mixed.py -v
```

`LOGIC_URL` hace que la prueba cree dos partidas del usuario nuevo directamente en Game Logic (un usuario recién registrado
no tiene historial). `PROFILE_URL` hace que espere hasta 20 s (`E2E_PROFILE_WAIT`) a que RabbitMQ cree el perfil. Sin
ninguna de las dos, todo es simulado y las pruebas pasan sin Docker.

**5. La app**: emulador con `BASE_URL=http://10.0.2.2:8090/` (ya configurado).

Notas: en modo mixto con Auth real y Profile simulado, el perfil se inventa (`usuario-<id>`) porque el simulado no
conoce a usuarios que registró Auth. Para ver "No disponible" en Inicio con el simulado puro: `MOCK_FAIL=stats,recentGames`.

## Retiro de la lista plana (GWM-02)

Hecho: `_normalize_summary` y la paginación local se retiraron de `main.py`, junto con las pruebas `test_legacy_*`. La prueba
`test_paginated_list_passes_through_untouched` cubre el formato `GamesPage` y `test_plain_list_is_no_longer_accepted` cubre el rechazo de la lista plana.
