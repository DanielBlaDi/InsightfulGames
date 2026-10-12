# Game Service (Single Player) — tarea 7

Java 21 + Spring Boot 3 (Maven). Puerto `8083`. Nombre en Compose: `single-player-component`.
Sigue el contrato del Prototipo 1 (secciones 3.4, 5 y 6). No guarda partidas: el estado vive en **Game Logic** (`:8082`).
Botcito se llama a través del Gateway: `POST {GATEWAY_INTERNAL_URL}/engine/best-move`.

## Variables de entorno
| Variable | Default | Uso |
|---|---|---|
| `GAME_LOGIC_URL` | `http://localhost:8082` | Game Logic |
| `GATEWAY_INTERNAL_URL` | `http://localhost:8080` | Gateway (ruta `/engine/*` hacia Botcito) |

## Rutas
REST (el Gateway envía siempre `X-User-Id`; sin esa cabecera responde `401 UNAUTHORIZED`):
`POST /games`, `GET /games`, `GET /games/{id}`, `POST /games/{id}/resign`, `GET /health`.

WebSocket: `/ws/games/{id}`. El Gateway valida `?token=` y reenvía `X-User-Id`.
Cierra con `4401` si falta el usuario y con `4404` si la partida no existe o es de otro usuario.

Cliente → servidor: `{"type":"move","uci":"e2e4"}` y `{"type":"resign","side":"white"}` (`side` solo en modo local).
Servidor → cliente: `state`, `move_rejected`, `bot_thinking`, `game_over`.

Extensión al contrato (avisar al grupo): mensaje `{"type":"error","code":"...","message":"..."}` para fallos que no son
una jugada rechazada (Botcito caído, Game Logic caído) y códigos `SERVICE_UNAVAILABLE` (502) y `BOT_UNAVAILABLE`.

## Tests automáticos
```bash
mvn test
```
`SinglePlayerServiceTest` simula Game Logic, Botcito y los canales: turnos, bot, mate, rendición, dueño de la partida y fallos de Botcito.

## Prueba manual (PowerShell, con todo levantado)
```powershell
# 1. Desde Backend/: Mongo + Game Logic + Single Player
docker compose -f docker-compose.dev.yml up --build

# 2. (solo modo vs_bot) en otra terminal, Botcito falso
pip install chess
python GameService/tools/fake_botcito.py

# 3. Crear una partida local
$u = "7d1f9d5e-3c2b-4f0e-9a41-0b5f6d7a8c90"
$g = Invoke-RestMethod -Method Post -Uri http://localhost:8083/games -Headers @{"X-User-Id"=$u} -ContentType "application/json" -Body '{"mode":"local"}'
$g.gameId

# 4. Jugar por WebSocket (npm i -g wscat)
wscat -c "ws://localhost:8083/ws/games/$($g.gameId)" -H "X-User-Id: $u"
> {"type":"move","uci":"f2f3"}
> {"type":"move","uci":"e7e5"}
> {"type":"move","uci":"g2g4"}
> {"type":"move","uci":"d8h4"}      # llega state y luego game_over: white/black, checkmate
```
Partida contra el bot:
`-Body '{"mode":"vs_bot","level":5,"playerColor":"white"}'`. Cada jugada tuya produce `state`, `bot_thinking` y `state`.
Con `"playerColor":"black"` la respuesta de `POST /games` ya trae la primera jugada del bot.
