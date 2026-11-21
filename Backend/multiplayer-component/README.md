# Multiplayer component

Servicio de partidas online, separado de `GameService` (Single Player). Está escrito
en Go 1.24 y escucha en el puerto `8084`. Es un **hub de sesiones**: mantiene las conexiones
WebSocket, la presencia de los jugadores y los plazos de reconexión, y envía a los clientes lo que
cambia. No tiene base de datos.

**Todo lo que cambia una partida lo orquesta el gateway web** (`Backend/api-gateway`, módulos
`orchestration/multiplayer.py` y `ws_session.py`): crear la partida (con `Idempotency-Key`), unirse, leerla,
rendirse, cambiar la visibilidad y las acciones por WebSocket (`move`, `resign`, `draw_*`). El gateway llama a
Game Logic y, tras cada cambio, avisa a este hub con `POST /internal/multiplayer/matches/{id}/publish`.
Este servicio ya no expone esas rutas REST ni opera en Game Logic por su cuenta.

## Arquitectura

```text
Gateway web ── REST y frames WS ──> Game Logic     (crear, unirse, leer, rendirse, jugar, tablas, visibilidad)
    │                  └── publish ────> Multiplayer    (el hub avisa por WebSocket y ajusta sus plazos)
    └── WebSocket (conexión, ping) ────> Multiplayer
                                          ├── GET Game Logic (estado al conectar; abandono por el timer)
                                          └── RabbitMQ: game.finished
```

Game Logic es fuente de verdad de `GameState`, `matchId`, `creationKey` y `requestFingerprint`. El
servicio mantiene únicamente sesiones WebSocket, una caché `matchId -> gameId` y plazos de reconexión
en memoria. Por ello, despliega una sola réplica, como especifica el contrato.

El hub conserva solo lo que depende de las conexiones: la presencia (`opponent_connected` y
`opponent_disconnected`), el plazo de reconexión (el abandono por el timer llama directamente a Game Logic) y
el consumidor de `game.finished`. Del cliente solo atiende `ping` (responde `pong`).

## Ejecutar

Requiere Go 1.24 y acceso a Game Logic y a RabbitMQ:

```powershell
$env:GAME_LOGIC_URL = "http://localhost:8082"
$env:RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"
go run ./cmd/multiplayer
```

Variables:

| Variable | Default | Uso |
|---|---|---|
| `PORT` | `8084` | Puerto HTTP |
| `LOG_LEVEL` | `INFO` | Nivel de logging (`DEBUG`, `INFO`, `WARN`, `ERROR`) |
| `GAME_LOGIC_URL` | `http://game-logic-component:8082` | Game Logic, llamado directamente (sin pasar por el gateway) |
| `RABBITMQ_URL` | requerida | Broker para consumir `multiplayer.game-finished` |
| `RECONNECT_WINDOW_SECONDS` | `30` | Ventana (1–600 s) para volver cuando el turno corresponde al jugador desconectado |
| `WS_ALLOWED_ORIGINS` | vacío | Lista separada por comas. Vacía delega la validación al Gateway |

Build y pruebas:

```powershell
go test ./...
go build ./cmd/multiplayer
```

## Rutas y protocolo

- `GET /health`
- `POST /internal/multiplayer/matches/{id}/publish` (lo llama el gateway)
- `GET /internal/multiplayer/ws/matches/{id}`

`publish` recibe `{ "state": GameState, "gameOver"?: false, "events"?: [...] }` y responde `204`. El hub actualiza la
sesión con ese estado (así el plazo de reconexión sabe de quién es el turno), lo envía como `state` a los
clientes de la partida (con `lastMove` si hay jugadas) y, si la partida terminó, envía `game_over` justo
después y cancela los plazos. `events` admite `draw_offered`, `draw_declined` y `draw_cancelled`; se envían tras el
`state` y antes del `game_over`. `gameOver: false` omite el `game_over` (cambio de visibilidad de una
partida terminada). **Guarda de orden:** un `state` con una `version` menor que la de la sesión se ignora;
la misma versión se acepta. No consulta a nadie. `400 VALIDATION_ERROR` si falta `state`, no es un
GameState o su `matchId` no coincide con la ruta; `404 MATCH_NOT_FOUND` si el id no es un UUID.

El gateway público mapea `/ws/matches/{id}` a la ruta WebSocket, verifica Origin y sesión antes de abrirla y
establece `X-User-Id`; el hub comprueba que el usuario participe (cierres `4401`/`4404`). La conexión envía
`state` al conectar. De los mensajes del cliente, el gateway reenvía solo `ping` al hub y atiende `move`,
`resign` y `draw_offer|accept|decline|cancel` por su cuenta, en orden por conexión, con un lock por partida:

- **Errores al cliente que actuó** (con los mismos mensajes del servicio original): `error` para JSON inválido
  (`Invalid JSON message`), tipo desconocido (`Unknown message type`), `move requires uci and expectedVersion`,
  `MATCH_NOT_FOUND`, `GAME_NOT_IN_PROGRESS`, `NOT_YOUR_TURN` y las reglas de tablas (`DRAW_ALREADY_OFFERED`,
  `DRAW_NOT_ALLOWED`); `move_rejected` para una jugada con versión vieja (`VERSION_CONFLICT`) o rechazada por
  Game Logic (con su código y mensaje).
- **Resultado a todos, por `publish`:** `state` (con `lastMove` si hay jugadas), el evento de tablas
  (`draw_offered` con `by`, `draw_declined`, `draw_cancelled`; `draw_accept` no tiene evento) y, si la partida
  terminó, `game_over` justo después. Tras un fallo que indica que el estado cambió (`GAME_FINISHED`,
  `GAME_NOT_IN_PROGRESS`, `VERSION_CONFLICT`, `CLOCK_EXPIRED`) el gateway publica el estado vigente antes de
  responder el error.
- Una acción que Game Logic ya aceptó se publica aunque el cliente se desconecte.

Las reglas de creación (huella canónica con los valores por omisión, `creationKey` por usuario,
validaciones) y el mapeo de errores de Game Logic (`GAME_NOT_FOUND` → `MATCH_NOT_FOUND`,
`GAME_NOT_WAITING` → `MATCH_NOT_WAITING`, 502/503/504 → `SERVICES_UNAVAILABLE`...) viven ahora en el
gateway. La idempotencia no se simula con estado local: la clave y la huella se envían a Game Logic para
persistirse atómicamente.
