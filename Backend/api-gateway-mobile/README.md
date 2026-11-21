# API Gateway móvil

Contrato técnico definitivo (secciones 4.11 y 5). FastAPI, puerto 8090. **Orquesta llamando directamente a los servicios**
(Auth, Profile/Stats y Game Logic, rutas `/internal/<servicio>/*` de cada uno). No depende del gateway web ni de ningún
gateway interno. Ya está en el `compose.yaml` raíz.

**Lista de partidas.** El contrato (4.1) define `GET /internal/logic/games` → `{items, nextCursor}` y Game Logic ya lo cumple
(GL-04). El gateway deja pasar esa respuesta sin transformarla: el cursor es opaco y la paginación la hace Game Logic.
Una lista plana o el formato anterior `{matches, cursor}` ya no se convierten; se responden como 502 `UPSTREAM_ERROR`.

| Ruta pública (app)        | Auth | Servicio y ruta                                                                    |
| ------------------------- | ---- | ---------------------------------------------------------------------------------- |
| `POST /auth/register`     | no   | Auth `POST /internal/auth/register`                                                |
| `POST /auth/login`        | no   | Auth `POST /internal/auth/login`                                                   |
| `GET /home`               | sí   | agrega (en paralelo) Profile `profile` + `stats` y Game Logic `games?limit=5`      |
| `GET /profile/me`         | sí   | Profile `GET /internal/profile/users/{userId}/profile`                             |
| `GET /stats/me`           | sí   | Profile `GET /internal/profile/users/{userId}/stats`                               |
| `DELETE /auth/account`    | sí   | Saga: Auth `GET users/{id}` → Logic → Tutor → Profile `DELETE users/{id}` → Auth `DELETE account` |
| `GET /games?limit&cursor` | sí   | Game Logic `GET /internal/logic/games?userId=&limit=&cursor=` (limit máx. 20)      |
| `GET /games/{id}`         | sí   | Game Logic `GET /internal/logic/games/{id}`: solo `local` y `vs_bot`, con visibilidad |
| `GET /matches/{id}`       | sí   | Game Logic `GET /internal/logic/games/by-match/{id}`: solo `multiplayer`, con visibilidad |

- **Visibilidad (regla del gateway).** El detalle solo se entrega al participante o si la partida es `shared`; si no, 404
  (`GAME_NOT_FOUND` / `MATCH_NOT_FOUND`). Un `GET /games/{id}` sobre una partida multiplayer, o un `GET /matches/{id}` sobre una
  local o vs_bot, también es 404.
- `userId` sale del claim `sub` del JWT (solo HS256, debe ser UUID; HS384/HS512 se rechazan). El cliente nunca lo envía.
- Descarta cualquier `X-User-Id` del cliente y no lo envía a ningún servicio: las rutas que usa el gateway móvil no lo necesitan.
- `/internal/*` desde fuera → 404. Sin cookies y sin rutas del Tutor (solo lo llama el borrado de cuenta).
- **Borrado de cuenta** (`DELETE /auth/account` → 204). El gateway orquesta, en orden: Auth `GET /internal/auth/users/{id}`
  (404 = ya no existe → 204 sin más llamadas), Game Logic `DELETE /internal/logic/users/{id}`, el paso del Tutor (lista sus
  partidas con `game-ids`, lee la visibilidad **actual** de cada una en Game Logic y llama a `erase` con las `shared` en
  `keepGameIds`; todo lo demás se borra, fail-closed), Profile/Stats `DELETE /internal/profile/users/{id}` (cada borrado
  debe dar 204) y, al final, Auth `DELETE /internal/auth/account` (solo borra la fila). Si un paso falla se corta
  la cadena con 503 `SERVICES_UNAVAILABLE` nombrando el servicio, no se borra la fila de Auth y el usuario puede reintentar
  (los borrados son idempotentes). Tope de la saga: 4 × `HTTP_TIMEOUT`. El cliente descarta su token al recibir 204.
- `/home`: cada sección es independiente (`null` + nombre en `unavailable`); 503 `SERVICES_UNAVAILABLE`
  solo si no se llega a ningún servicio. `recentGames` es el `items` de la lista (5 más recientes).
- Errores traducidos según el servicio de origen (`GAME_NOT_FOUND` / `MATCH_NOT_FOUND` / `INVALID_CREDENTIALS` / `USERNAME_TAKEN`).
  Game Logic responde `GAME_NOT_FOUND` también para un `matchId` desconocido; el gateway lo entrega como `MATCH_NOT_FOUND`.
- Solo emite códigos del catálogo 4.12. Un método no soportado responde 404 `NOT_FOUND`; un 409 o 422 de un servicio sin formato de error común responde 502 `UPSTREAM_ERROR`.
- Un id de ruta que no es UUID responde 404 sin llamar a ningún servicio.
- No arranca sin `JWT_SECRET`.

## Variables

`PORT=8090`, `JWT_SECRET` (obligatoria), `JWT_ALGORITHM=HS256` (otro valor impide el arranque), `HTTP_TIMEOUT=15`, `LOG_LEVEL`,
y la URL base de cada servicio:

| Variable         | Por omisión                         |
| ---------------- | ----------------------------------- |
| `AUTH_URL`       | `http://auth-component:8081`        |
| `GAME_LOGIC_URL` | `http://game-logic-component:8082`  |
| `PROFILE_URL`    | `http://profile-stats-component:8087` |
| `TUTOR_URL`      | `http://tutor-component:8085` (solo para el borrado de cuenta) |

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest -q     # las e2e se omiten si no defines MOBILE_GATEWAY_URL
```

| Archivo                   | Qué prueba                                                                                              | Necesita             |
| ------------------------- | ------------------------------------------------------------------------------------------------------- | -------------------- |
| `tests/test_gateway.py`   | El gateway móvil contra servicios simulados con `httpx.MockTransport`                                    | nada                 |
| `tests/test_e2e_mixed.py` | Registro, login, perfil, estadísticas, inicio, historial paginado y detalle contra **procesos reales**  | `MOBILE_GATEWAY_URL` |

## Probar con servicios reales y/o simulados

Como cada servicio tiene su propia URL, se mezcla real y simulado apuntando cada variable donde corresponda.
`tools/fake_services.py` simula Auth, Profile/Stats y Game Logic en un solo puerto.

```bash
cd Backend/api-gateway-mobile
export JWT_SECRET=<el mismo de tu .env, 32 bytes o más>

# Todo simulado
uvicorn --app-dir tools fake_services:app --port 8080
AUTH_URL=http://localhost:8080 PROFILE_URL=http://localhost:8080 GAME_LOGIC_URL=http://localhost:8080 \
  uvicorn main:app --port 8090

# Mezcla: Auth y Game Logic reales (publicados con compose.debug.yaml), Profile simulado
AUTH_URL=http://localhost:8081 GAME_LOGIC_URL=http://localhost:8082 PROFILE_URL=http://localhost:8080 \
  uvicorn main:app --port 8090
```

Pruebas de punta a punta:

```bash
MOBILE_GATEWAY_URL=http://localhost:8090 \
LOGIC_URL=http://localhost:8082 PROFILE_URL=http://localhost:8087 \
  pytest tests/test_e2e_mixed.py -v
```

`LOGIC_URL` hace que la prueba cree dos partidas del usuario nuevo directamente en Game Logic (un usuario recién registrado
no tiene historial). `PROFILE_URL` hace que espere hasta 20 s (`E2E_PROFILE_WAIT`) a que RabbitMQ cree el perfil. Sin
ninguna de las dos, todo es simulado y las pruebas pasan sin Docker.

La app: emulador con `BASE_URL=http://10.0.2.2:8090/` (ya configurado).

Notas: con Auth real y Profile simulado, el perfil no existe porque el simulado no conoce a usuarios que registró Auth.
Para ver "No disponible" en Inicio con el simulado puro: `MOCK_FAIL=stats,recentGames`.
