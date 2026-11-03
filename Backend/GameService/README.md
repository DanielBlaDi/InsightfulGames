# Single Player

Java 21 + Spring Boot 3.3.5 (Maven). Puerto `8083`. Nombre en Compose: `single-player-component`.
La carpeta conserva el nombre histórico `GameService`.

Coordina las partidas de un solo usuario: `local` (dos personas en la misma pantalla) y `vs_bot`
(contra el motor). Autoriza cada acción, mantiene la sesión WebSocket y gestiona el turno del bot.
No tiene base propia: el estado vive en Game Logic, que es la única fuente de verdad.

Toda comunicación con otros servicios pasa por el gateway interno:

| Destino | Ruta |
|---|---|
| Game Logic | `{GATEWAY_INTERNAL_URL}/internal/logic/*` |
| Botcito-juego | `POST {GATEWAY_INTERNAL_URL}/internal/engine/best-move` con `{ fen, botLevel }` |

## Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `SERVER_PORT` | `8083` | Puerto HTTP y WebSocket |
| `GATEWAY_INTERNAL_URL` | `http://localhost:8080` | Gateway interno (Game Logic y Botcito) |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672` | Consumo de `game.finished` |

## Rutas REST

Todas reciben `X-User-Id`, que pone el gateway. Sin esa cabecera responden `401 UNAUTHORIZED`.

| Ruta | Cuerpo | Respuesta | Quién |
|---|---|---|---|
| `POST /internal/single-player/games` | `{ mode, botLevel, playerColor, timeControl, visibility }` | `201 GameState` | Usuario autenticado |
| `GET /internal/single-player/games/{id}` | — | `200 GameState` | Participante, o cualquiera si es `shared` |
| `POST /internal/single-player/games/{id}/resign` | `{ side }` solo en local | `200 GameState` | Participante |
| `PATCH /internal/single-player/games/{id}/visibility` | `{ visibility, expectedVersion }` | `200 GameState` | Participante |
| `GET /health` | — | `200 { "status": "ok" }` | — |

Reglas de creación:

- `mode`: `local` o `vs_bot`.
- `botLevel` (1 a 20) y `playerColor` (`white` o `black`): obligatorios solo en `vs_bot`; en local se ignoran.
- `timeControl`: `null` o `{ "minutes": 10 }`.
- `visibility`: `private` (por defecto) o `shared`.
- El cuerpo que recibe Game Logic lo arma este servicio: en local, dos participantes con el mismo
  `userId` (uno por color); en vs_bot, uno solo, el humano.
- Si el humano juega con negras, el bot abre antes de responder. Si el bot falla, la partida se devuelve igual.

Una partida multijugador, o una en la que el usuario no participa, responde `404 GAME_NOT_FOUND`.

## WebSocket

`/internal/single-player/ws/games/{id}`. La ruta pública `/ws/games/{id}` la atiende el gateway web,
que valida Origin y sesión y reenvía `X-User-Id`. Solo para participantes.

| Dirección | Mensaje |
|---|---|
| Cliente | `{ "type": "move", "uci": "e2e4", "expectedVersion": 3 }` |
| Cliente | `{ "type": "resign", "side": "white" }` (`side` solo en local) |
| Servidor | `{ "type": "state", "state": GameState, "lastMove"? }` |
| Servidor | `{ "type": "move_rejected", "code", "message" }` |
| Servidor | `{ "type": "bot_thinking" }` |
| Servidor | `{ "type": "game_over", "result", "endReason" }` |
| Servidor | `{ "type": "error", "code", "message" }` |

- `state` se envía completo al conectar (sin `lastMove`) y tras cada cambio, incluida la visibilidad.
  `game_over` va justo después del `state` final.
- `move_rejected`: la acción del cliente no se aceptó. Corresponde a los errores 400, 409 y 422:
  `VALIDATION_ERROR`, `VERSION_CONFLICT`, `GAME_NOT_IN_PROGRESS`, `INVALID_MOVE`, `NOT_YOUR_TURN`,
  `GAME_FINISHED` y `CLOCK_EXPIRED`.
- Con `VERSION_CONFLICT` o `CLOCK_EXPIRED`, el servidor envía antes el `state` vigente (y `game_over`
  si el reloj terminó la partida), para que el cliente juegue con la versión correcta.
- `error`: fallo ajeno a la jugada que no cambia la partida, como `SERVICES_UNAVAILABLE`,
  `ENGINE_BUSY` o `ENGINE_TIMEOUT`.
- Cierres: `4401` sin usuario, `4404` partida inexistente o usuario que no participa.

Si Botcito falla, la jugada humana queda guardada, se envía `error` y la partida sigue en turno del
bot. Al reconectar, Single Player retoma ese turno. El cliente nunca repite su jugada.

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
| `SinglePlayerServiceTest` | Cuerpo de creación por modo, participantes, turno, bot, `expectedVersion`, rendición, visibilidad y `game.finished`, con dependencias simuladas |
| `SinglePlayerIntegrationTest` | El servicio real, REST y WebSocket, contra un gateway interno falso que hace de Game Logic y Botcito. Verifica rutas, cuerpos, versiones, errores, cierres y la notificación de fin |
| `GameStateContractTest` | El GameState del contrato pasa sin perder campos, y los mensajes tienen la forma exacta |
| `GameFinishedListenerTest` | Filtro por modo, DLQ y reintentos |

## Prueba manual

Con Game Logic en `:8082`, levanta el gateway interno falso y luego Single Player:

```bash
pip install chess
GAME_LOGIC_URL=http://localhost:8082 python tools/fake_botcito.py     # puerto 8000
GATEWAY_INTERNAL_URL=http://localhost:8000 mvn spring-boot:run
```

```bash
U=7d1f9d5e-3c2b-4f0e-9a41-0b5f6d7a8c90
curl -s -X POST localhost:8083/internal/single-player/games -H "X-User-Id: $U" \
     -H 'Content-Type: application/json' -d '{"mode":"local"}'

# npm i -g wscat
wscat -c "ws://localhost:8083/internal/single-player/ws/games/<gameId>" -H "X-User-Id: $U"
> {"type":"move","uci":"f2f3","expectedVersion":0}
> {"type":"move","uci":"e7e5","expectedVersion":1}
> {"type":"move","uci":"g2g4","expectedVersion":2}
> {"type":"move","uci":"d8h4","expectedVersion":3}   # llega state y luego game_over
```

Contra el bot: `-d '{"mode":"vs_bot","botLevel":5,"playerColor":"black"}'`. La respuesta ya trae la
primera jugada del bot.
