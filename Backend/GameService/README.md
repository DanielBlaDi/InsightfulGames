# Game Service — tarea 7 (modos de juego + canal WebSocket)

Java 21 + Spring Boot 3 (Maven). Puerto `8083`.
Habla con **Game Logic** (tarea 6, puerto `8082`) por REST y con **Botcito** (tarea 8) por REST.

## Correr
```bash
# Todo junto (Mongo + Game Logic + Game Service), desde Backend/
docker compose -f docker-compose.dev.yml up --build

# Solo este servicio, sin Game Logic ni Mongo (perfil mock con chesslib)
SPRING_PROFILES_ACTIVE=mock mvn spring-boot:run

# Solo este servicio contra un Game Logic ya levantado
GAMELOGIC_URL=http://localhost:8082 mvn spring-boot:run
```
Variables: `GAMELOGIC_URL` (default `http://localhost:8082`), `BOTCITO_URL` (default `http://botcito:8000`).
Health check: `GET /actuator/health`

## Probar sin frontend
```bash
npm i -g wscat
wscat -c ws://localhost:8083/ws/game
> {"type":"create_game","mode":"LOCAL","playerId":1}
> {"type":"move","move":"f2f3"}
> {"type":"move","move":"e7e5"}
> {"type":"move","move":"g2g4"}
> {"type":"move","move":"d8h4"}      # jaque mate -> game_over BLACK_WINS
```

## Protocolo WebSocket  (endpoint `/ws/game`)

Cliente -> servidor
| type | campos |
|---|---|
| `create_game` | `mode` (`LOCAL`/`BOT`), `difficulty` (1-20, default 10), `color` (`WHITE`/`BLACK`, solo BOT), `playerId` (opcional) |
| `move` | `move` en UCI: `e2e4`; promoción con 5.º carácter: `e7e8q` |
| `resign` | — |

Servidor -> cliente
| type | campos |
|---|---|
| `game_created` | `gameId` (= ID de la partida en MongoDB), `mode`, `fen`, `turn` |
| `game_state` | `gameId`, `fen`, `turn`, `lastMove` |
| `game_over` | `gameId`, `result` (`WHITE_WINS`/`BLACK_WINS`/`DRAW`), `reason` (`CHECKMATE`/`STALEMATE`/`DRAW_RULE`/`RESIGNATION`) |
| `error` | `message` |

## IDs de jugador que se guardan en Game Logic
- Usuario logueado: el API Gateway debe enviar el header `X-User-Id` (sacado del JWT, y borrar el que mande el cliente). Si no llega, se usa `playerId` del mensaje.
- Sin identificar: `-1` (invitado).
- Botcito: `0`.
- Modo LOCAL: las blancas y las negras usan el mismo ID (mismo dispositivo y cuenta).

## Qué guarda Game Logic
- `create_game` -> `POST /matches` (devuelve el ID de la partida).
- cada jugada -> `PATCH /matches/{id}/movements` (valida, guarda y devuelve FEN + resultado).
- fin de partida (mate, tablas o abandono) -> `PATCH /matches/{id}/result`.

## Contratos con otras tareas
- **Tarea 8 (Botcito):** `POST {BOTCITO_URL}/best-move` con `{"fen","level"}` -> `{"move":"e7e5"}`.
- **Tarea 2 (Gateway):** proxy de WebSocket hacia `ws://game-service:8083/ws/game` y header `X-User-Id`.
- **Tarea 1 (Infra):** agregar `game-logic` (8082), `game-service` (8083) y Mongo al `docker-compose.yml` real.
  `Backend/docker-compose.dev.yml` es solo para pruebas locales.

## Pendiente
- Multijugador en línea (RF-15), desconexión/reconexión (RF-23) y Elo.
