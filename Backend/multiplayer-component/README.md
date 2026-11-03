# Multiplayer component

Servicio de partidas online, separado de `GameService` (Single Player). Está escrito
en Go 1.24 y expone las rutas internas del contrato en el puerto `8084`.

## Arquitectura

```text
Gateway web
    ├── REST / WebSocket ──> Multiplayer
    │                          ├── HTTP interno ──> Gateway interno ──> Game Logic
    │                          └── RabbitMQ: game.finished
    └── añade X-User-Id tras validar la sesión
```

Multiplayer no tiene base de datos. Game Logic es fuente de verdad de `GameState`,
`matchId`, `creationKey` y `requestFingerprint`. El servicio mantiene únicamente
sesiones WebSocket, una caché `matchId -> gameId` y plazos de reconexión en memoria.
Por ello, despliega una sola réplica, como especifica el contrato.

## Ejecutar

Requiere Go 1.24 y acceso al Gateway interno y a RabbitMQ:

```powershell
$env:GATEWAY_INTERNAL_URL = "http://localhost:8080"
$env:RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"
go run ./cmd/multiplayer
```

Variables:

| Variable | Default | Uso |
|---|---|---|
| `PORT` | `8084` | Puerto HTTP |
| `LOG_LEVEL` | `INFO` | Nivel de logging (`DEBUG`, `INFO`, `WARN`, `ERROR`) |
| `GATEWAY_INTERNAL_URL` | `http://api-gateway-component:8080` | Gateway web en modo interno |
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
- `POST /internal/multiplayer/matches` (`Idempotency-Key` obligatoria)
- `POST /internal/multiplayer/matches/{id}/join`
- `GET /internal/multiplayer/matches/{id}`
- `POST /internal/multiplayer/matches/{id}/resign`
- `PATCH /internal/multiplayer/matches/{id}/visibility`
- `GET /internal/multiplayer/ws/matches/{id}`

El Gateway público debe mapear `/matches/*` y `/ws/matches/{id}` a las rutas
internas correspondientes, verificar la sesión antes del upgrade y establecer
`X-User-Id`. La conexión WS envía `state` al conectar y acepta `move`, `resign`,
`ping` y acciones `draw_*`. El servidor serializa cambios por partida y transmite
`state` antes de `game_over`.

`POST /matches` aplica los valores por defecto antes de calcular la huella canónica.
El mismo `Idempotency-Key` produce la misma partida porque la clave y la huella se
envían a Game Logic para persistirse atómicamente; Multiplayer no simula idempotencia
con estado local.

## Integración pendiente en el repositorio

El Game Logic que actualmente está en el repositorio implementa rutas de single
player, no las rutas nuevas del contrato necesarias por Multiplayer
(`/internal/logic/games/{id}/join`, `/abandon`, `/draw/*`, `by-match` y
`expectedVersion`). El Gateway también debe implementar los passthrough REST/WS y
añadir `MULTIPLAYER_URL`. Este componente sigue el contrato definitivo; necesita esas
interfaces desplegadas para completar una partida integrada.