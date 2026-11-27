# Databases
- Deleted empty .gitkeep file.
- Renamed /Databases to /database
## Auth
- Removed the redundant named UNIQUE constraint.
## Mongo
- Replaced the custom `js_escape` function with `jq` JSON string escaping.
- Removed unnecessary escaping logic.
- Prevented problems with special characters, quotes and newlines in environment variables.
- Kept the original MongoDB user creation logic unchanged.

**Notes**
- `jq` must be installed in the environment running the script.
- MongoDB Shell (`mongosh`) must be available.
## Profile
- Replaced `TIMESTAMP WITH TIME ZONE` with its PostgreSQL equivalent shorthand, `TIMESTAMPTZ`.
- Standardized column formatting and spacing.
- Adjusted the `stats` foreign key formatting for readability.

**Notes**
- The PostgreSQL global session requires `SET TIME ZONE 'UTC';`. TODO
## README.MD
- Included the notes in the MD.

# Backend
- renamed /Backend to /backend
## API Gateway
- Reorganized the orchestration imports for readability.
- Split a few long calls and response constructions across lines.
- Removed an unnecessary trailing comma in `error_response`.

## Mobile API Gateway
- `games_page()` now validates that `nextCursor` is present and is either a string or `null`.
- Invalid Game Logic pagination responses are rejected as unexpected, matching the documented response format.
- Fixed `username` and `password` validation to prevent errors when receiving null or invalid data types.
- Separated credential retrieval during registration to avoid unnecessary dictionary access.
- Added cursor validation in `list_games`.
- Invalid cursors and negative offsets now return HTTP 400 instead of causing internal server errors. 
- Improved formatting of lists, conditions, and dictionaries for readability.
- Removed unnecessary whitespace and line breaks.

#### MD

- Added the missing `/health` endpoint to the route table.
- Clarified that client-provided `X-User-Id` headers are discarded, while the gateway may send its own validated user ID to Auth during account deletion.
- Corrected the `/home` failure behavior: a 503 is returned only when all three upstream services are unreachable due to connection failures.
- Clarified that `fake_services.py` only simulates a subset of Game Logic.
- Documented that the mock does not implement account deletion, local game creation, moves, or resignation.
- Clarified the mock testing scope and the operations that require real services.
- Made the JWT startup requirements explicit: `JWT_SECRET` must contain at least 32 bytes and `JWT_ALGORITHM` must be `HS256`.

## Reverse Proxy
### escenarios / medir_resistencia.py
- Removed the unused `statistics` import.
- Adjustments in the MD to make it consistent with the code

### secure-channel
- Fixed certificate validity dates to use timezone-naive UTC datetimes, as required by the cryptography certificate builder.
- Prevented a StopIteration error when a Nginx map block has no closing brace, allowing malformed configurations to be reported instead of crashing the validator.
- Clarified the HTTP behavior of both entries to match their actual route handling: API requests are blocked instead of redirected, and other mobile HTTP requests are rejected. (Dockerfile)


## Timeout Worker
- Deleted unnecessary clutter: .gradle/, build/, .gitattributes

## botcito
- Added the missing HTML document structure with explicit head and body elements.
- Prevented unnecessary close calls when the WebSocket is already closed.
- Corrected the API docstring, which incorrectly described the service as stateless.
- Updated the engine pool docstring to accurately describe its process management and locking.
- Removed an unused lock from StockfishEngine.
- Cleaned up spacing and class declarations.
- Corrected the service description to cover both Botcito-juego and Botcito-análisis.
- Clarified the different inputs and outputs of each service.
- Aligned the introduction with the current API implementation.

## analysis-worker broker
- Removed the unused ACTION_REQUEUE import.

## calculation
- Removed the unused SAN fallback, since legal moves already generate SAN through python-chess.

## config
- Added validation to reject NaN and infinite values in floating-point environment variables.

## repository
- Removed an unused `_now` field from the recovery aggregation pipeline.

## Gateway Shared
- Added UUID v4 version validation for analysis game IDs.
- Fixed single-player timeControl validation to reject unexpected fields.
## Multiplayer Component
### http go
- Moved WebSocket origin validation into the upgrader's `CheckOrigin` callback so unauthorized origins are rejected before the connection is established.
- Removed the redundant origin check after the WebSocket upgrade.
- Rejects disallowed WebSocket origins during the handshake instead of after upgrading the connection.
- Rechecks processed RabbitMQ event IDs after acquiring the match lock to prevent concurrent duplicate deliveries from broadcasting the same finished state more than once.

## Profile stats component
- Validate game.finished mode values against multiplayer, local, and vs_bot; unsupported or missing values now go directly to the dead-letter queue instead of being retried or silently marked as processed.
- Validate non-null result values and participant colors against the allowed values, so invalid values are dead-lettered.
- Updated the README to describe the invalid-event handling.

## timeoutworker - timeout service
- Corrected the cycle summary log level so empty cycles are logged at DEBUG instead of INFO.
- Clarified that processing stops when Game Logic becomes unreachable.

## Tutor component
- Removed leftover `elif kind == "http": await resource.aclose()` branch in `lifespan` cleanup.
- Removed unused `http_timeout` field from `Settings` and `Settings.from_env`.
- Removed unused `_float_env` helper function.
- Removed unused `get_database` helper function and `AsyncIOMotorDatabase` import. 
- Normalized and validated `game.participantIds` with `normalize_uuid(p, "participantIds")` in `request_analysis` instead of keeping raw strings.
- Fixed broken numbering in the `POST /internal/tutor/analyses` algorithm list (`1, 3, 4...` to `1, 2, 3...`).
- Added note specifying that `participantIds` must contain valid UUIDs and are normalized/deduplicated.
- Removed obsolete `HTTP_TIMEOUT` entry from the environment variables table and `compose.yaml` snippet.

## Backend documentation
- Removed trailing slash from `GET /matches/{gameId}/` in section 4.3 rule 10 to match the REST endpoint definition (`GET /matches/{id}`) in sections 5 and 7.
- Completed missing `Resultado` cell in test case #11 of section 9 (`error` "Jugada ilegal: e2e5" / HTTP 400).
- Added missing environment variable `PORT` (default `8083`) to the Game Service environment variables table in section 8 to align with sections 1 and 4.

# Frontend
- Only renamed to /frontend. Not gonna review frontend bruh


# Rendimiento
- Added a `ws.onclose` handler in `bot-ws.js` so premature socket disconnections cleanly terminate the game, clear pending timers, and record `bot_partida_ok` as failed instead of hanging until the 60s timeout.
- Added CLI argument count validation and a safe fallback (`psutil.cpu_count() or 1`) in `monitor.py` to avoid `IndexError` or `ZeroDivisionError` when running the monitor standalone.
- Added an exit code check after running `preparar.js` in `ejecutar.ps1` so the test runner aborts early if user setup fails rather than running load tests with stale or missing tokens.
- Documented `CLAVE_USUARIOS` and `USUARIOS` environment variables in `README.md` to match the configuration options exposed in `comun.js` and `preparar.js`.