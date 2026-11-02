# Tutor (`tutor-component`)

Componente lógico del Prototipo 2. Implementa la **sección 13** del contrato
(`Documentación/contracts_v9.docx.md`): recibe solicitudes de análisis, verifica
que la partida exista, esté terminada y sea visible, crea el análisis una sola
vez, publica `tutor.analysis.requested` para el Analysis Worker y entrega el
informe. También atiende el borrado de cuenta de la sección 7.

- Puerto: **8085** (`PORT`).
- Rutas: solo `/internal/tutor/*` y `GET /health`. El gateway web publica
  `/tutor/*` y traduce.
- Base de datos: MongoDB de análisis (contenedor propio, sección 18).
- Mensajería: exchange `tutor.events` (topic, durable), routing key
  `tutor.analysis.requested` (sección 17).
- El Tutor **no** llama a Botcito, no evalúa posiciones, no calcula `cpLoss` ni
  clasificaciones. Eso es del Analysis Worker (sección 14).

## Estructura

```
tutor-component/
├── main.py                 # FastAPI, lifespan, handlers de error, /health
├── app/
│   ├── config.py           # Settings desde el entorno (sección 21)
│   ├── db.py               # cliente Motor
│   ├── repository.py       # colección analyses + índices
│   ├── models.py           # DTO de entrada/salida y vista del documento
│   ├── validation.py       # UUID, depth, textos → VALIDATION_ERROR
│   ├── errors.py           # ApiError con { error: { code, message } }
│   ├── game_logic.py       # GET /internal/logic/games/{id} y visibilidad
│   ├── events.py           # publicación AMQP persistente y robusta
│   ├── explanation.py      # explicación determinista (LLM_PROVIDER=mock)
│   ├── service.py          # reglas de negocio
│   ├── routes.py           # rutas /internal/tutor/*
│   └── timeutils.py        # fechas ISO 8601 UTC
├── tests/                  # pytest + mongomock + dobles de Game Logic/RabbitMQ
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── pytest.ini
```

## Rutas

| Método | Ruta | Respuesta |
| :--- | :--- | :--- |
| `POST` | `/internal/tutor/analyses` | **202** análisis nuevo (`pending`); **200** si ya existía uno con la misma clave |
| `GET` | `/internal/tutor/analyses/{analysisId}` | **200** estado del análisis |
| `GET` | `/internal/tutor/analyses/{analysisId}/result` | **200** informe; **409** `ANALYSIS_NOT_READY` si no está `completed` |
| `DELETE` | `/internal/tutor/users/{userId}` | **204** siempre (idempotente) |
| `GET` | `/health` | **200** `{ "status": "ok" }`; **503** si Mongo de análisis no responde |

Las tres primeras leen la identidad de la cabecera `X-User-Id` que añade el
gateway web. Sin cabecera o con un UUID inválido responden `401 UNAUTHORIZED`.
El `DELETE` lo llama Auth por el gateway interno y no usa `X-User-Id`.

### POST /internal/tutor/analyses

```json
{
  "gameId": "11111111-1111-4111-8111-111111111111",
  "language": "es",
  "detailLevel": "standard",
  "depth": 15
}
```

- `depth` es opcional; por defecto `ANALYSIS_DEPTH_DEFAULT` (15). Fuera de
  `1..ANALYSIS_DEPTH_MAX` → `400 VALIDATION_ERROR`.
- La clave del análisis es `(gameId, engineVersion, language, detailLevel, depth)`.
  `engineVersion` sale de `ENGINE_VERSION` y solo lo decide el Tutor.
- Si ya existe, devuelve `200` con el mismo `analysisId` y **no** republica.
- Si no existe, guarda `status: pending`, publica el evento y responde `202`.
- Si la publicación en RabbitMQ falla, el análisis queda en `pending` y la
  respuesta sigue siendo `202`: el polling del Analysis Worker (sección 14) lo
  recupera. No se devuelve 503 por un fallo de publicación.

### GET /internal/tutor/analyses/{id}

```json
{
  "analysisId": "uuid",
  "gameId": "uuid",
  "status": "pending",
  "engineVersion": "stockfish-17",
  "depth": 15,
  "language": "es",
  "detailLevel": "standard",
  "createdAt": "2026-11-01T15:30:00Z",
  "updatedAt": "2026-11-01T15:30:00Z",
  "error": null
}
```

Estados: `pending` (lo crea el Tutor), `processing` / `completed` / `failed` (los
escribe el worker). Cuando `failed`, `error` trae el mensaje seguro que muestra
el frontend.

### GET /internal/tutor/analyses/{id}/result

Solo con `status: completed`. Devuelve la forma de la sección 13:

```json
{
  "analysisId": "uuid",
  "gameId": "uuid",
  "engineVersion": "stockfish-17",
  "depth": 15,
  "language": "es",
  "detailLevel": "standard",
  "summary": { "white": { "...": 0 }, "black": { "...": 0 } },
  "moves": [ { "ply": 1, "classification": "best", "...": "..." } ],
  "explanation": "texto generado por el Tutor (mock)",
  "createdAt": "2026-11-01T15:30:00Z"
}
```

`summary` y `moves` se entregan tal como los escribió el worker. Si están
anidados en `result: { summary, moves }` (forma canónica) o en la raíz del
documento, el Tutor acepta ambas. `explanation` se genera de forma determinista
a partir de `summary` la primera vez que se lee y se guarda en el documento;
no se regenera en lecturas posteriores.

### Visibilidad (regla clave de la sección 13)

- `shared`: cualquiera que pueda ver la partida puede pedir y leer el análisis.
- `private`: solo los `participantIds` de la partida.
- La visibilidad se consulta a Game Logic **en cada lectura**. El análisis no
  guarda una copia para autorizar: si la partida pasa de `private` a `shared`
  o al revés, el acceso cambia en la siguiente consulta.
- El análisis pertenece a la partida, no a quien lo pidió: dos usuarios con la
  misma clave reciben el mismo `analysisId`.

### DELETE /internal/tutor/users/{userId}

1. Reemplaza `requestedBy` por `00000000-0000-0000-0000-000000000000`.
2. Borra los análisis con `visibility: "private"` del snapshot y el usuario en
   `participantIds`.
3. Conserva los análisis de partidas `shared`, incluso los que pidió el usuario.
4. Responde `204` aunque no exista nada. Es idempotente.

Se usa el **snapshot** `participantIds` / `visibility` guardado al crear el
análisis, no el estado actual de la partida: Game Logic puede haber anonimizado
ya al usuario cuando Auth llama al Tutor.

## Variables de entorno

| Variable | Defecto | Uso |
| :--- | :--- | :--- |
| `PORT` | `8085` | Puerto HTTP |
| `GATEWAY_INTERNAL_URL` | `http://api-gateway-component:8080` | Base para `GET /internal/logic/games/{id}` |
| `MONGO_ANALYSIS_URL` | `mongodb://localhost:27017` | URI completa de Mongo de análisis |
| `MONGO_ANALYSIS_DATABASE` | `insightful_analysis` | Base de datos |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | Broker |
| `ENGINE_VERSION` | `stockfish-17` | Parte de la clave; subirlo al cambiar umbrales o la imagen de Stockfish |
| `ANALYSIS_DEPTH_DEFAULT` | `15` | Profundidad si la petición no la envía |
| `ANALYSIS_DEPTH_MAX` | `18` | Tope; por encima → `VALIDATION_ERROR` |
| `LLM_PROVIDER` | `mock` | En esta entrega solo existe `mock` |
| `HTTP_TIMEOUT` | `10` | Timeout de las llamadas al gateway interno |
| `LOG_LEVEL` | `INFO` | Nivel de log |

## Ejecución local

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements-dev.txt
.\venv\Scripts\python -m pytest -q
.\venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8085
```

Las pruebas no necesitan Mongo ni RabbitMQ: usan `mongomock-motor` y dobles de
Game Logic y del publicador. Cubren validación, idempotencia, profundidad como
parte de la clave, visibilidad recalculada, estados, explicación, borrado de
cuenta y salud del servicio.

Prueba manual completa (requiere Game Logic v9, Mongo y RabbitMQ arriba):

```bash
curl -i http://localhost:8085/health

curl -i -X POST http://localhost:8085/internal/tutor/analyses \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' \
  -d '{"gameId":"11111111-1111-4111-8111-111111111111","language":"es","detailLevel":"standard","depth":15}'

curl -s http://localhost:8085/internal/tutor/analyses/<analysisId> \
  -H 'X-User-Id: aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

curl -s http://localhost:8085/internal/tutor/analyses/<analysisId>/result \
  -H 'X-User-Id: aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
```

Docker:

```bash
docker build -t tutor-component:dev .
docker run --rm -p 8085:8085 \
  -e GATEWAY_INTERNAL_URL=http://host.docker.internal:8080 \
  -e MONGO_ANALYSIS_URL=mongodb://host.docker.internal:27017 \
  -e RABBITMQ_URL=amqp://guest:guest@host.docker.internal:5672/ \
  tutor-component:dev
```

## Errores que devuelve

```json
{ "error": { "code": "GAME_NOT_FOUND", "message": "Texto legible" } }
```

| Código | HTTP | Cuándo |
| :--- | :--- | :--- |
| `VALIDATION_ERROR` | 400 | UUID inválido, `depth` fuera de rango, campos faltantes o cuerpo mal formado |
| `UNAUTHORIZED` | 401 | Falta `X-User-Id` o no es un UUID |
| `GAME_NOT_FOUND` | 404 | La partida no existe o no es visible al pedir el análisis |
| `GAME_NOT_FINISHED` | 409 | La partida sigue en curso |
| `ANALYSIS_NOT_FOUND` | 404 | El análisis no existe o su partida ya no es visible |
| `ANALYSIS_NOT_READY` | 409 | Resultado pedido antes de `completed` |
| `SERVICES_UNAVAILABLE` | 503 | Game Logic o Mongo de análisis no responden |
| `INTERNAL_ERROR` | 500 | Fallo no clasificado (solo diagnóstico interno) |

`ANALYSIS_FAILED` no es un error HTTP: se devuelve en `status` / `error` del
análisis (sección 20).

## Documento de MongoDB (handoff al Analysis Worker)

Colección `analyses` de la base `MONGO_ANALYSIS_DATABASE`. Un documento:

```json
{
  "_id": "analysisId (uuid)",
  "analysisId": "uuid",
  "gameId": "uuid",
  "engineVersion": "stockfish-17",
  "language": "es",
  "detailLevel": "standard",
  "depth": 15,
  "status": "pending",
  "requestedBy": "uuid",
  "participantIds": ["uuid"],
  "visibility": "private",
  "result": null,
  "error": null,
  "explanation": null,
  "createdAt": "ISODate",
  "updatedAt": "ISODate",
  "startedAt": null,
  "completedAt": null
}
```

Contrato con el worker:

- El Tutor crea el documento y es dueño del esquema, `requestedBy`,
  `participantIds`, `visibility`, `engineVersion` y `explanation`.
- El worker actualiza **solo** `status`, `result` y `error` (y opcionalmente
  `startedAt`, `completedAt`, `updatedAt`). Busca por `analysisId` (o `_id`, son
  el mismo valor).
- Forma canónica del resultado: `result = { "summary": {...}, "moves": [...] }`
  con los campos de la sección 13. Conviene marcarlo `completed` y escribir
  `result` en la misma operación.
- En fallo, `status: "failed"` y un `error` seguro (sin trazas ni datos internos).
- Estados válidos: `pending` → `processing` → `completed` | `failed`.

Índices creados por el Tutor:

```js
db.analyses.createIndex(
  { gameId: 1, engineVersion: 1, language: 1, detailLevel: 1, depth: 1 },
  { unique: true, name: "uq_analyses_key" }
)
db.analyses.createIndex(
  { requestedBy: 1, createdAt: -1 },
  { name: "ix_analyses_requested_by_created" }
)
```

> **Nota sobre la sección 18.** El índice del contrato omite `depth`, pero las
> secciones 13 y 14 incluyen `depth` en la clave de idempotencia y el evento lo
> transporta. Se implementa la clave de cinco campos; conviene corregir la
> sección 18 en la próxima revisión del documento.

Evento publicado:

```json
{
  "eventId": "uuid",
  "eventType": "tutor.analysis.requested",
  "occurredAt": "2026-11-01T15:25:00Z",
  "analysisId": "uuid",
  "gameId": "uuid",
  "requestedBy": "uuid",
  "language": "es",
  "detailLevel": "standard",
  "depth": 15
}
```

Se publica en el exchange `tutor.events` con `delivery_mode=2` (persistente),
`message_id = eventId` y routing key `tutor.analysis.requested`. El Tutor declara
el exchange, no la cola: `analysis-worker.requested` es del Analysis Worker.

## Integración pendiente (la aplica el equipo, no este componente)

Estos archivos son compartidos y **no se modificaron** desde este componente.

### `compose.yaml`

```yaml
  tutor-component:
    container_name: tutor-component
    restart: unless-stopped
    build:
      context: ./Backend/tutor-component
      dockerfile: Dockerfile
    image: tutor-component:dev
    expose:
      - "${TUTOR_PORT}"
    environment:
      PORT: "${TUTOR_PORT}"
      GATEWAY_INTERNAL_URL: http://api-gateway-component:${API_GATEWAY_PORT}
      MONGO_ANALYSIS_URL: "mongodb://${MONGO_ANALYSIS_USER}:${MONGO_ANALYSIS_PASSWORD}@mongo-analysis:${MONGO_ANALYSIS_PORT}/${MONGO_ANALYSIS_DATABASE}?authSource=admin"
      MONGO_ANALYSIS_DATABASE: "${MONGO_ANALYSIS_DATABASE}"
      RABBITMQ_URL: "amqp://${RABBITMQ_DEFAULT_USER}:${RABBITMQ_DEFAULT_PASS}@rabbitmq:${RABBITMQ_PORT}/"
      ENGINE_VERSION: "stockfish-17"
      ANALYSIS_DEPTH_DEFAULT: "15"
      ANALYSIS_DEPTH_MAX: "18"
      LLM_PROVIDER: "mock"
      HTTP_TIMEOUT: "15"
      LOG_LEVEL: "INFO"
    depends_on:
      mongo-analysis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    networks:
      - app

  mongo-analysis:
    image: mongo:7
    container_name: mongo-analysis-db
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_ANALYSIS_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ANALYSIS_PASSWORD}
      MONGO_INITDB_DATABASE: ${MONGO_ANALYSIS_DATABASE}
    expose:
      - "${MONGO_ANALYSIS_PORT}"
    volumes:
      - mongo-analysis-data:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping').ok"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - app

  rabbitmq:
    image: rabbitmq:3.13-management
    container_name: rabbitmq-broker
    restart: unless-stopped
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_DEFAULT_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_DEFAULT_PASS}
    expose:
      - "${RABBITMQ_PORT}"
    volumes:
      - rabbitmq-data:/data
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 20s
    networks:
      - app
```

Añadir al bloque `volumes:` → `mongo-analysis-data:` y `rabbitmq-data:`.
La consola de administración **no** se publica en `compose.yaml`; solo en
`compose.override.yaml` de desarrollo:

```yaml
services:
  rabbitmq:
    ports:
      - "${RABBITMQ_MANAGEMENT_PORT}:15672"
```

### `.env.example` (sin valores reales)

```dotenv
# ==========================================
# TUTOR / ANÁLISIS
MONGO_ANALYSIS_PORT=27017
MONGO_ANALYSIS_DATABASE=
MONGO_ANALYSIS_USER=
MONGO_ANALYSIS_PASSWORD=

# ==========================================
# RABBITMQ
RABBITMQ_PORT=5672
RABBITMQ_MANAGEMENT_PORT=15672
RABBITMQ_DEFAULT_USER=
RABBITMQ_DEFAULT_PASS=
```

### Gateway web (`Backend/api-gateway/main.py`)

| Ruta pública | Ruta interna | Identidad |
| :--- | :--- | :--- |
| `POST /tutor/analyses` | `POST /internal/tutor/analyses` | `X-User-Id` del JWT |
| `GET /tutor/analyses/{id}` | `GET /internal/tutor/analyses/{id}` | `X-User-Id` del JWT |
| `GET /tutor/analyses/{id}/result` | `GET /internal/tutor/analyses/{id}/result` | `X-User-Id` del JWT |

- El gateway debe **añadir** `X-User-Id` (nunca aceptarlo del cliente) después
  de validar la cookie y reenviar el cuerpo tal cual.
- `DELETE /internal/tutor/users/{userId}` lo llama Auth por el gateway interno,
  sin JWT de usuario. No se publica hacia el exterior.
- **Importante:** el gateway actual reemplaza el cuerpo de error del servicio
  por un mapeo genérico por código HTTP. Para que el frontend reciba
  `GAME_NOT_FOUND`, `ANALYSIS_NOT_FOUND`, `ANALYSIS_NOT_READY`, etc., debe
  reenviar el `error.code` y `error.message` del Tutor (o mapear solo los 5xx).
- Variable nueva: `TUTOR_URL: http://tutor-component:${TUTOR_PORT}`.

El frontend consume `POST /api/tutor/analyses` (Vike quita `/api`) → gateway
`/tutor/analyses` → Tutor `/internal/tutor/analyses`. El polling de la sección 6
funciona contra `GET /api/tutor/analyses/{id}`.

## Fuera de alcance de esta entrega

- Proveedor real de LLM (`LLM_API_KEY`) y explicación durante la partida.
- Caché de explicaciones más allá de la clave de análisis (la explicación se
  guarda en el documento del análisis).
- Implementación del Analysis Worker (otro componente) y del GameState v9 con
  `visibility` / `participants` en Game Logic (otro componente).
