# API Gateway móvil

Contrato técnico definitivo (secciones 4.11 y 5). FastAPI, puerto 8090. Solo habla con el gateway interno (`GATEWAY_INTERNAL_URL`,
que en el compose es `api-gateway-component`, rutas `/internal/*`). Ya está en el `compose.yaml` raíz.

**Compatibilidad con el prototipo 1.** Game Logic aún responde `GET /logic/games` como lista simple, sin paginar y
sin `matchId`/`endReason`/`color`. Mientras sea así, este gateway la pagina (cursor opaco) y completa esos campos con `null`.
Si Game Logic ya responde `{items, nextCursor}` (contrato 4.1), la respuesta pasa tal cual. Esta compatibilidad es temporal: cuando Game Logic migre (GL-04) se retira (GWM-02).

| Ruta pública (app) | Auth | Interna |
|---|---|---|
| `POST /auth/register` | no | `POST /internal/auth/register` |
| `POST /auth/login` | no | `POST /internal/auth/login` |
| `GET /home` | sí | agrega profile + stats + `logic/games?limit=5` |
| `GET /profile/me` | sí | `GET /internal/profile/users/{userId}/profile` |
| `GET /stats/me` | sí | `GET /internal/profile/users/{userId}/stats` |
| `GET /games?limit&cursor` | sí | `GET /internal/logic/games?userId=&limit=&cursor=` (limit máx. 20) |
| `GET /games/{id}` | sí | `GET /internal/single-player/games/{id}` (local, vs_bot) |
| `GET /matches/{id}` | sí | `GET /internal/multiplayer/matches/{id}` (multiplayer) |

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
pytest -q          # 54 pruebas, gateway interno simulado con httpx.MockTransport
```

## Desarrollo sin backend completo
Mientras el gateway web real no publique `/internal/*` (ni existan Profile/Stats y Multiplayer):
```bash
export JWT_SECRET=una-clave-larga-de-desarrollo-123456789
uvicorn --app-dir tools fake_internal_gateway:app --port 8080        # gateway interno simulado
GATEWAY_INTERNAL_URL=http://localhost:8080 uvicorn main:app --port 8090
MOCK_FAIL=stats uvicorn --app-dir tools fake_internal_gateway:app --port 8080   # para ver "No disponible"
```
