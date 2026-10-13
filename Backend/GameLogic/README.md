# Game Logic — tarea 6

Java 21 + Spring Boot 4 (Gradle) + chesslib + MongoDB. Puerto `8082`. Nombre en Compose: `game-logic-component`.
Sigue el contrato del Prototipo 1 (secciones 3.5, 3.8 y 4). Solo lo llama Single Player.

Es la **única fuente de verdad** de cada partida: guarda el FEN, las jugadas y el resultado, y valida cada jugada
contra la posición guardada (el cliente solo manda la jugada en `uci`, ya no el FEN).

## Rutas
| Ruta | Respuesta |
|---|---|
| `POST /logic/games` `{userId, mode, botLevel, playerColor}` | 201 `GameState` |
| `GET /logic/games/{id}` | 200 `GameState` / 404 `GAME_NOT_FOUND` |
| `GET /logic/games?userId=` | 200 `[GameSummary]` (la más reciente primero) |
| `POST /logic/games/{id}/moves` `{uci}` | 200 `GameState` / 422 `INVALID_MOVE` o `GAME_FINISHED` |
| `POST /logic/games/{id}/resign` `{side}` | 200 `GameState` / 422 `GAME_FINISHED` |
| `GET /health` | 200 `{"status":"ok"}` |

Errores: `{ "error": { "code": "...", "message": "..." } }` (`VALIDATION_ERROR` 400, `GAME_NOT_FOUND` 404,
`INVALID_MOVE` y `GAME_FINISHED` 422). Detecta jaque mate, ahogado, material insuficiente, regla de 50 jugadas y
repetición triple (la posición se reconstruye desde `initialFen` y las jugadas guardadas).

## Variables de entorno
`MONGO_URL` (por defecto `mongodb://localhost:27017/games`; también acepta el nombre antiguo `MONGODB_URI`).

## Tests y documentación
```bash
./gradlew test          # Windows: gradlew.bat test
./gradlew asciidoctor   # genera la documentación de la API
```
- `ChessRulesTest`: reglas de ajedrez, sin Spring ni Mongo.
- `ChessApplicationHTTPTests`: las rutas del contrato con un repositorio simulado (no necesita Mongo). También generan
  los fragmentos (snippets) de REST Docs que usa `src/docs/asciidoc/index.adoc`.
- `ChessApplicationBasicTests`: que el contexto de Spring arranque.

La documentación queda en `build/docs/asciidoc/index.html`.

Para ejecutarlo en local hace falta MongoDB: `docker run -p 27017:27017 mongo:7` y luego `./gradlew bootRun`.
