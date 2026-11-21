# Single Player

Java 21 + Spring Boot 3.3.5 (Maven). Puerto `8083`. Nombre en Compose: `single-player-component`.
La carpeta conserva el nombre histórico `GameService`.

Coordina las partidas de un solo usuario: `local` (dos personas en la misma pantalla) y `vs_bot`
(contra el motor). Es un **hub de sesiones**: mantiene las conexiones WebSocket, envía el estado inicial a
quien se conecta y avisa a los clientes de lo que cambia. No tiene base propia ni decide nada del juego: el
estado vive en Game Logic, que es la única fuente de verdad.

**Todo lo que cambia una partida lo orquesta el gateway web** (`Backend/api-gateway`, módulos
`orchestration/single_player.py` y `ws_session.py`): crear, leer, rendirse, cambiar la visibilidad, las
jugadas, el turno del bot y las respuestas `move_rejected` / `error` al cliente. El gateway llama a Game
Logic y a Botcito y, tras cada cambio, avisa a este hub con `POST .../publish`. Este servicio ya no llama a
Botcito ni expone rutas REST de juego.

Única llamada saliente, directa y de solo lectura (sin gateway), para el estado inicial al conectar y para
`game.finished`:

| Destino | Ruta |
|---|---|
| Game Logic | `GET {GAME_LOGIC_URL}/internal/logic/games/{id}` |

## Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `SERVER_PORT` | `8083` | Puerto HTTP y WebSocket |
| `GAME_LOGIC_URL` | `http://localhost:8082` | Game Logic |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672` | Consumo de `game.finished` |

## Rutas

| Ruta | Cuerpo | Respuesta | Quién |
|---|---|---|---|
| `POST /internal/single-player/games/{id}/publish` | `{ state?, lastMove?, gameOver?, signal? }` | `204` | El gateway |
| `GET /health` | — | `200 { "status": "ok" }` | — |

`publish` envía a los clientes conectados a esa partida, sin consultar a nadie:

- `state`: GameState vigente (con `version`, obligatoria y del mismo `gameId` que la ruta). Se envía como
  `{ type: "state" }` y, si la partida terminó, `game_over` justo después. `gameOver: false` omite el
  `game_over` (el gateway lo usa al cambiar la visibilidad de una partida terminada).
- `lastMove`: última jugada (uci), se omite si no hubo jugada.
- `signal`: aviso sin cambio de estado. `{ type: "bot_thinking" }` o `{ type: "error", code, message }`.
- **Guarda de orden:** un `state` con `version` menor que la última enviada a esa partida se ignora (un
  aviso atrasado no hace retroceder al cliente); la misma versión se acepta (reenvío del estado vigente).
  Sin sesiones abiertas no hace nada. `400 VALIDATION_ERROR` si falta `state` y `signal`, si el `gameId`
  no coincide, si falta `version` o si el `signal` es inválido.

Las reglas de creación (modo, `botLevel`, `playerColor`, `timeControl`, `visibility`, participantes por
modo) y de visibilidad de la partida (participante, o `shared` para leer) las aplica ahora el gateway.
Una partida multijugador, o una en la que el usuario no participa, responde `404 GAME_NOT_FOUND`.

## WebSocket

`/internal/single-player/ws/games/{id}`. La ruta pública `/ws/games/{id}` la atiende el gateway web, que
valida Origin y sesión, comprueba que el usuario participe y abre este WebSocket con `X-User-Id`. Este hub
es **solo de salida**: registra la sesión, envía el `state` inicial y reenvía lo que llega por `publish` y por
`game.finished`. Los mensajes del cliente no llegan aquí: el gateway los atiende y, si llegara alguno
directamente, se ignora.

Mensajes del cliente (los procesa el gateway, en orden por conexión):

| Dirección | Mensaje |
|---|---|
| Cliente | `{ "type": "move", "uci": "e2e4", "expectedVersion": 3 }` |
| Cliente | `{ "type": "resign", "side": "white" }` (`side` solo en local) |
| Servidor | `{ "type": "state", "state": GameState, "lastMove"? }` (por el hub) |
| Servidor | `{ "type": "move_rejected", "code", "message" }` (lo envía el gateway al cliente que actuó) |
| Servidor | `{ "type": "bot_thinking" }` (por el hub) |
| Servidor | `{ "type": "game_over", "result", "endReason" }` (por el hub) |
| Servidor | `{ "type": "error", "code", "message" }` (por el hub, o el gateway al cliente que actuó) |

- `state` se envía completo al conectar (sin `lastMove`) y tras cada cambio, incluida la visibilidad.
  `game_over` va justo después del `state` final.
- `move_rejected`: la acción no se aceptó (errores 400, 409 y 422: `VALIDATION_ERROR`, `VERSION_CONFLICT`,
  `GAME_NOT_IN_PROGRESS`, `INVALID_MOVE`, `NOT_YOUR_TURN`, `GAME_FINISHED`, `CLOCK_EXPIRED`).
- Con `VERSION_CONFLICT` o `CLOCK_EXPIRED`, el gateway publica antes el `state` vigente (y el hub envía
  `game_over` si el reloj terminó la partida) para que el cliente juegue con la versión correcta.
- `error`: fallo ajeno a la jugada que no cambia la partida, como `SERVICES_UNAVAILABLE`, `ENGINE_BUSY`,
  `ENGINE_TIMEOUT` o `GAME_NOT_FOUND`.
- Cierres: `4401` sin usuario, `4404` partida inexistente o usuario que no participa.

Si Botcito falla, la jugada humana queda guardada, el gateway publica una señal `error` y la partida sigue en
turno del bot. Al reconectar, el gateway retoma ese turno en segundo plano. El cliente nunca repite su
jugada. Una jugada que Game Logic ya aceptó se publica aunque el cliente se desconecte.

## Errores

Forma común: `{ "error": { "code": "...", "message": "..." } }`. Los errores de Game Logic y de
Botcito pasan con su código y estado reales. Una dependencia caída, o un 5xx fuera del catálogo,
responde `503 SERVICES_UNAVAILABLE`. `ENGINE_BUSY` llega como 503 y `ENGINE_TIMEOUT` como 504.

## Eventos

Consume `game.finished` desde la cola `single-player.game-finished`, enlazada a `game.events`, con sus
colas `.wait` (reintento a los 5 s) y `.dlq`. Para partidas local y vs_bot, relee la partida y envía
`state` y `game_over` a las sesiones abiertas. Así se enteran de un fin por tiempo o por borrado de
cuenta. Sin sesiones abiertas no hace nada, por lo que un mensaje repetido es inofensivo.

Un mensaje inválido va directo a la `.dlq`. Si falla la lectura de la partida, se reintenta hasta
cinco veces y luego va a la `.dlq`.

## Pruebas

```bash
mvn test
```

| Clase | Qué cubre |
|---|---|
| `SinglePlayerServiceTest` | `publish` (orden, guarda de versión, señales, validación), participantes del WebSocket y `game.finished`, con dependencias simuladas |
| `SinglePlayerIntegrationTest` | El servicio real (`publish` y WebSocket) contra un Game Logic falso. Verifica que las rutas REST ya no existen, `publish` sin consultar a nadie, la guarda de versión, que el hub ignora los frames del cliente, el cierre de no participantes y la notificación de fin |
| `GameStateContractTest` | El GameState del contrato pasa sin perder campos, y los mensajes tienen la forma exacta |
| `GameFinishedListenerTest` | Filtro por modo, DLQ y reintentos |

## Prueba manual

Las partidas se crean y se juegan por el gateway web (`POST /games`, WebSocket `/ws/games/{id}`). Aquí se puede
crear una partida directamente en Game Logic, conectarse al hub y simular un aviso del gateway:

```bash
U=7d1f9d5e-3c2b-4f0e-9a41-0b5f6d7a8c90
curl -s -X POST localhost:8082/internal/logic/games -H 'Content-Type: application/json' \
     -d "{\"mode\":\"local\",\"visibility\":\"private\",\"timeControl\":null,\"botLevel\":null,\"participants\":[{\"userId\":\"$U\",\"color\":\"white\"},{\"userId\":\"$U\",\"color\":\"black\"}]}"

# npm i -g wscat
wscat -c "ws://localhost:8083/internal/single-player/ws/games/<gameId>" -H "X-User-Id: $U"
# llega el state inicial; las jugadas ya no se envían aquí sino al gateway (/api/ws/games/{id})

# Aviso del gateway (lo que llega al wscat de arriba)
curl -i -X POST localhost:8083/internal/single-player/games/<gameId>/publish \
     -H 'Content-Type: application/json' -d '{"signal":{"type":"bot_thinking"}}'
```
