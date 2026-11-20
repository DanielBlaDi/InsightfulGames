# Tutor (`tutor-component`)

Componente lógico del Prototipo 2. Implementa la **sección 16** del contrato
vigente (`Documentación/CONTRATO_TECNICO_DEFINITIVO.docx.md`): recibe
solicitudes de análisis, valida que la partida exista, esté terminada y sea
analizable, crea el análisis una sola vez por clave, publica
`tutor.analysis.requested` para el Analysis Worker, reactiva fallos transitorios
y entrega el informe con su explicación.

También atiende el **paso 2 de la saga de borrado de cuenta** (sección 16.4.4):
consulta la visibilidad actual de cada partida en Game Logic, borra los análisis
de las partidas privadas y anonimiza los que se conservan de partidas `shared`.

- Puerto: **8085** (`PORT`).
- Rutas: solo `/internal/tutor/*` y `GET /health`. El gateway web publica
  `/tutor/*` y traduce.
- Base de datos: MongoDB de análisis (contenedor propio, sección 18).
- Mensajería: exchange `tutor.events` (topic, durable), routing key
  `tutor.analysis.requested` (sección 17).
- El Tutor **no** llama a Botcito, no evalúa posiciones, no calcula `cpLoss` ni
  clasificaciones. Eso es del Analysis Worker (sección 17).
- La explicación es simulada (`LLM_PROVIDER=mock`).

## Estructura

```
tutor-component/
├── main.py                 # FastAPI, lifespan, handlers de error, /health
├── app/
│   ├── config.py           # Settings desde el entorno (sección 16.5)
│   ├── db.py               # cliente Motor
│   ├── repository.py       # colección analyses, índices, reactivación y borrado
│   ├── models.py           # DTO, retryable y vista del documento
│   ├── validation.py       # UUID, depth, textos → VALIDATION_ERROR
│   ├── errors.py           # ApiError con { error: { code, message } }
│   ├── game_logic.py       # GET /internal/logic/games/{id} y visibilidad
│   ├── events.py           # publicación AMQP con confirms y mandatory
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
| `POST` | `/internal/tutor/analyses` | **202** análisis nuevo o reactivado (`pending`); **200** si ya existía y no es reactivable |
| `GET` | `/internal/tutor/analyses/{analysisId}` | **200** estado del análisis |
| `GET` | `/internal/tutor/analyses/{analysisId}/result` | **200** informe; **409** `ANALYSIS_NOT_READY` si no está `completed` |
| `DELETE` | `/internal/tutor/users/{userId}` | **204** siempre (idempotente) |
| `GET` | `/health` | **200** `{ "status": "ok" }`; **503** si Mongo no responde o falta el índice único |

Las tres rutas de análisis leen la identidad de la cabecera `X-User-Id` que
añade el gateway web después de validar el JWT. Sin cabecera o con un UUID
inválido responden `401 UNAUTHORIZED`. El `DELETE` lo llama Auth por el gateway
interno y no usa `X-User-Id`.

## POST /internal/tutor/analyses

```json
{
  "gameId": "11111111-1111-4111-8111-111111111111",
  "language": "es",
  "detailLevel": "standard",
  "depth": 15
}
```

- `language` y `detailLevel` son texto libre; por defecto `es` y `standard`.
- `depth` es opcional; por defecto `ANALYSIS_DEPTH_DEFAULT` (15). Fuera de
  `1..ANALYSIS_DEPTH_MAX` → `400 VALIDATION_ERROR`.
- La clave del análisis es `(gameId, engineVersion, language, detailLevel, depth)`.
  `engineVersion` sale de `ENGINE_VERSION` y solo lo decide el Tutor.

Algoritmo (sección 16.4.1):

1. Valida el formato.
2. Lee la partida de Game Logic. Sin acceso o inexistente →
   `404 GAME_NOT_FOUND`.
3. `status` distinto de `finished` → `409 GAME_NOT_FINISHED`.
4. `endReason == expired` o sin jugadas → `409 GAME_NOT_ANALYZABLE`. La
   comprobación de `GAME_NOT_FINISHED` va antes, de modo que una partida
   `expired` nunca responde `GAME_NOT_FINISHED`.
5. Busca la clave, protegida por el índice único.
6. Si no existe: crea `status: pending`, publica el evento y responde `202`.
7. Si existe y no es reactivable: responde `200` con ese análisis y **no**
   republica.
8. Si existe, está `failed` y es reactivable: aplica la reactivación atómica y
   responde `202`.

Si la publicación en RabbitMQ falla, el análisis queda en `pending` y la
respuesta sigue siendo `202`: el polling del Analysis Worker (sección 17) lo
recupera. **Un fallo de publicación nunca devuelve 503.**

## GET /internal/tutor/analyses/{id}

```json
{
  "analysisId": "uuid",
  "gameId": "uuid",
  "status": "failed",
  "engineVersion": "stockfish-15.1",
  "depth": 15,
  "language": "es",
  "detailLevel": "standard",
  "createdAt": "2026-11-01T15:30:00Z",
  "updatedAt": "2026-11-01T15:30:00Z",
  "error": "El motor no respondió",
  "retryable": true
}
```

Estados: `pending` (lo crea el Tutor), `processing` / `completed` / `failed` (los
escribe el worker). `error` es un texto seguro o `null`.

`retryable` **no se guarda**: se calcula en cada respuesta y es `true` solo si el
análisis está `failed`, `failureKind == "transient"` y
`reactivations < ANALYSIS_MAX_REACTIVATIONS`. Con
`ANALYSIS_MAX_REACTIVATIONS=0` la reactivación está desactivada y `retryable`
siempre es `false`.

La visibilidad se consulta a Game Logic **en cada lectura**. Si la partida ya no
es visible para el usuario, la respuesta es `404 ANALYSIS_NOT_FOUND`.

## GET /internal/tutor/analyses/{id}/result

Solo con `status: completed`. Devuelve la forma de la sección 16.4.2:

```json
{
  "analysisId": "uuid",
  "gameId": "uuid",
  "engineVersion": "stockfish-15.1",
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
a partir de `summary` la primera vez que se lee y se guarda en el documento; no
se regenera en lecturas posteriores. Si `averageCpLoss` es `null`, la
explicación muestra «no disponible» en lugar de un `0` falso.

## Reactivación de fallos (sección 16.4.3)

| Caso | Resultado del POST |
| :--- | :--- |
| `failed` + `failureKind: transient` + `reactivations < máximo` | Actualización atómica a `pending`, limpia `error`, `failureKind`, `leaseUntil`, `leaseOwner` y `claimCount`, suma `reactivations`, publica un evento nuevo y responde **202** |
| `failed` + `failureKind: permanent` | Responde **200** con `failed` y `retryable: false`; no republica |
| `failed` + sin `failureKind` | Responde **200** con `failed` y `retryable: false`; no republica |
| `reactivations` igual al máximo | Responde **200** con `failed` y `retryable: false`; no reprocesa esa clave |
| Dos POST simultáneos | Solo uno reactiva; el otro responde **200**. Una sola publicación |

La reactivación conserva `analysisId`, la clave y el `requestedBy` original. El
evento nuevo lleva un `eventId` distinto. Pedir otra `depth` es otro análisis.

## Visibilidad (sección 16.4.2)

- `shared`: cualquier usuario con sesión que pueda ver la partida puede pedir y
  leer el análisis.
- `private`: solo los `participantIds` de la partida.
- Cualquier otro valor, incluido `null`, **no es visible**. La decisión es
  fail-closed y usa solo `visibility` y `participants`; no se usan `userId` ni
  `createdBy`.
- El análisis pertenece a la partida, no a quien lo pidió: dos usuarios con la
  misma clave reciben el mismo `analysisId`.
- No se guarda ninguna copia de la visibilidad en el documento de análisis.

## DELETE /internal/tutor/users/{userId}

Paso 2 de la saga de borrado. Es idempotente y responde `204` exista o no el
usuario. El algoritmo (sección 16.4.4) es de **dos fases**:

1. Busca los `gameId` distintos de análisis cuyo `participantIds` contiene al
   usuario.
2. Resuelve la visibilidad actual de **todos** los `gameId` en Game Logic. Si
   falla la disponibilidad, responde `503` **sin mutar ningún análisis**. Auth
   conserva su fila y el usuario puede reintentar.
3. Solo cuando ya están todas las decisiones:
   - `private` o partida inexistente: borra **todos** los análisis de ese
     `gameId`, incluso los pedidos por otros usuarios.
   - `shared`: conserva los análisis y reemplaza el `userId` por el anónimo en
     `participantIds`.
4. Reemplaza `requestedBy` por `00000000-0000-0000-0000-000000000000` en todos
   los análisis del usuario.

La anonimización de `participantIds` es idempotente, deduplicada y tolera que el
anónimo ya estuviera presente. Si el `userId` recibido es el propio valor
anónimo, la operación no hace nada.

## Variables de entorno

| Variable | Defecto | Uso |
| :--- | :--- | :--- |
| `PORT` | `8085` | Puerto HTTP |
| `GATEWAY_INTERNAL_URL` | `http://api-gateway-component:8080` | Base para `GET /internal/logic/games/{id}` |
| `MONGO_ANALYSIS_URL` | `mongodb://localhost:27017` | URI completa de Mongo de análisis |
| `MONGO_ANALYSIS_DATABASE` | `insightful_analysis` | Base de datos |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | Broker |
| `ENGINE_VERSION` | `stockfish-15.1` | Parte de la clave; debe coincidir con el motor real |
| `ANALYSIS_DEPTH_DEFAULT` | `15` | Profundidad si la petición no la envía |
| `ANALYSIS_DEPTH_MAX` | `18` | Tope; por encima → `VALIDATION_ERROR` |
| `ANALYSIS_MAX_REACTIVATIONS` | `3` | Reactivaciones por análisis; `0` las desactiva; debe ser `>= 0` |
| `LLM_PROVIDER` | `mock` | En esta entrega solo existe `mock` |
| `HTTP_TIMEOUT` | `15` | Timeout de las llamadas al gateway interno |
| `LOG_LEVEL` | `INFO` | Nivel de log |

`RABBITMQ_TIMEOUT` (5 s por defecto) es un ajuste interno del publicador, no una
variable del contrato: evita que un broker lento retrase la respuesta.

## Persistencia y contrato con el Analysis Worker

Colección `analyses` de la base `MONGO_ANALYSIS_DATABASE`. Un documento:

```json
{
  "_id": "analysisId (uuid)",
  "analysisId": "uuid",
  "gameId": "uuid",
  "engineVersion": "stockfish-15.1",
  "language": "es",
  "detailLevel": "standard",
  "depth": 15,
  "status": "pending",
  "requestedBy": "uuid",
  "participantIds": ["uuid"],
  "error": null,
  "explanation": null,
  "createdAt": "ISODate",
  "updatedAt": "ISODate",
  "reactivations": 0
}
```

No existe el campo `visibility`: la visibilidad siempre se consulta a Game
Logic. Tampoco se escriben los campos de resultado ni de lease salvo en la
transición de reactivación, que los limpia según el contrato.

| Dueño | Campos |
| :--- | :--- |
| Tutor | `_id`, `analysisId`, `gameId`, `engineVersion`, `language`, `detailLevel`, `depth`, `requestedBy`, `participantIds`, `explanation`, `createdAt`, `reactivations` |
| Analysis Worker | `result`, `failureKind`, `startedAt`, `completedAt`, `leaseUntil`, `leaseOwner`, `claimCount` |
| Ambos, solo en las transiciones de estado y reactivación | `status`, `error`, `updatedAt` |

- `result` tiene la forma `{ summary, moves }`.
- En fallo, el worker escribe `status: "failed"`, `failureKind` (`transient` o
  `permanent`) y un `error` seguro (sin trazas ni datos internos).
- Un worker que termine después de un borrado no encuentra el documento y
  descarta el resultado.

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
db.analyses.createIndex(
  { participantIds: 1 },
  { name: "ix_analyses_participant_ids" }
)
```

`/health` verifica **en cada llamada** que `uq_analyses_key` exista, sea único y
cubra exactamente los cinco campos de la clave. Si falta o está mal definido,
responde `503`.

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
`message_id = eventId`, `content_type=application/json`, `mandatory=true`,
`publisher_confirms=true` y `on_return_raises=true`. No hay reintento de
publicación. El Tutor declara el exchange, no la cola: `analysis-worker.requested`
es del Analysis Worker.

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
| `GAME_NOT_ANALYZABLE` | 409 | La partida expiró o no tiene jugadas |
| `ANALYSIS_NOT_FOUND` | 404 | El análisis no existe o su partida ya no es visible |
| `ANALYSIS_NOT_READY` | 409 | Resultado pedido antes de `completed` o sin `summary`/`moves` |
| `SERVICES_UNAVAILABLE` | 503 | Game Logic o Mongo de análisis no responden, o falta el índice único |
| `INTERNAL_ERROR` | 500 | Fallo no clasificado (solo diagnóstico interno) |

`ANALYSIS_FAILED` no es un error HTTP: se devuelve en `status` / `error` del
análisis.

## Pruebas

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements-dev.txt
.\venv\Scripts\python -m pytest -q
```

Las **65 pruebas** no necesitan Mongo ni RabbitMQ: usan `mongomock-motor` y
dobles de Game Logic y del publicador. Cubren:

- validación, idempotencia y `depth` como parte de la clave;
- `GAME_NOT_ANALYZABLE` para partidas expiradas o sin jugadas;
- visibilidad fail-closed y recalculada en cada lectura;
- estados, explicación, promedio nulo y explicación en inglés;
- reactivación transitoria, permanente, sin `failureKind`, máximo alcanzado y
  dos POST simultáneos;
- borrado según la visibilidad actual, anonimización y deduplicación de
  `participantIds`, fallo de Game Logic sin mutaciones y borrado idempotente;
- `/health` sin el índice único, índice de participantes y tolerancia a Mongo
  caído;
- flags de publicación (`publisher_confirms`, `on_return_raises`, `mandatory`).

**Validación pendiente:** MongoDB y RabbitMQ reales, concurrencia sobre el
índice único y la publicación no se han probado todavía contra infraestructura
real. Queda aplazada hasta tener Compose levantado.

## Ejecución local

```powershell
.\venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8085
```

Prueba manual (requiere Game Logic con `visibility`/`participants`, Mongo y
RabbitMQ arriba):

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

curl -i -X DELETE http://localhost:8085/internal/tutor/users/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
```

Docker:

```bash
docker build -t tutor-component:dev .
docker run --rm -p 8085:8085 \
  -e GATEWAY_INTERNAL_URL=http://host.docker.internal:8080 \
  -e MONGO_ANALYSIS_URL=mongodb://host.docker.internal:27017 \
  -e MONGO_ANALYSIS_DATABASE=insightful_analysis \
  -e RABBITMQ_URL=amqp://guest:guest@host.docker.internal:5672/ \
  tutor-component:dev
```

## Integración pendiente (la aplica el equipo, no este componente)

Estos archivos son compartidos y **no se modificaron** desde este componente.

### `compose.yaml`

```yaml
  mongo-analysis:
    image: mongo:7
    container_name: mongo-analysis-db
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_ANALYSIS_ROOT_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ANALYSIS_ROOT_PASSWORD}
      MONGO_INITDB_DATABASE: ${MONGO_ANALYSIS_DATABASE}

      MONGO_APP_DATABASE: ${MONGO_ANALYSIS_DATABASE}
      MONGO_APP_USERNAME: ${MONGO_ANALYSIS_USER}
      MONGO_APP_PASSWORD: ${MONGO_ANALYSIS_PASSWORD}
    expose:
      - "${MONGO_ANALYSIS_PORT}"
    volumes:
      - mongo-analysis-data:/data/db
      - ./Databases/mongo/init-mongo.sh:/docker-entrypoint-initdb.d/init-mongo.sh:ro
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping').ok"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - app

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
      MONGO_ANALYSIS_URL: "mongodb://${MONGO_ANALYSIS_USER}:${MONGO_ANALYSIS_PASSWORD}@mongo-analysis:${MONGO_ANALYSIS_PORT}/${MONGO_ANALYSIS_DATABASE}?authSource=${MONGO_ANALYSIS_DATABASE}"
      MONGO_ANALYSIS_DATABASE: "${MONGO_ANALYSIS_DATABASE}"
      RABBITMQ_URL: "amqp://${RABBITMQ_DEFAULT_USER}:${RABBITMQ_DEFAULT_PASS}@rabbitmq:${RABBITMQ_PORT}/"
      ENGINE_VERSION: "stockfish-15.1"
      ANALYSIS_DEPTH_DEFAULT: "15"
      ANALYSIS_DEPTH_MAX: "18"
      ANALYSIS_MAX_REACTIVATIONS: "3"
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
```

Añadir al bloque `volumes:` → `mongo-analysis-data:`. El `mongo-analysis` debe
reutilizar `Databases/mongo/init-mongo.sh`, que crea el usuario de aplicación en
`MONGO_ANALYSIS_DATABASE`; por eso la URI usa
`authSource=${MONGO_ANALYSIS_DATABASE}`. El script no vuelve a ejecutarse si el
volumen ya existe.

### `.env.example` (sin valores reales)

```dotenv
# ==========================================
# TUTOR / ANÁLISIS
TUTOR_PORT=
MONGO_ANALYSIS_PORT=
MONGO_ANALYSIS_DATABASE=
MONGO_ANALYSIS_ROOT_USER=
MONGO_ANALYSIS_ROOT_PASSWORD=
MONGO_ANALYSIS_USER=
MONGO_ANALYSIS_PASSWORD=

# ==========================================
# RABBITMQ
RABBITMQ_PORT=
RABBITMQ_MANAGEMENT_PORT=
RABBITMQ_DEFAULT_USER=
RABBITMQ_DEFAULT_PASS=
```

### Gateway web (`Backend/api-gateway/main.py`)

| Ruta pública | Ruta interna | Identidad |
| :--- | :--- | :--- |
| `POST /tutor/analyses` | `POST /internal/tutor/analyses` | `X-User-Id` del JWT |
| `GET /tutor/analyses/{id}` | `GET /internal/tutor/analyses/{id}` | `X-User-Id` del JWT |
| `GET /tutor/analyses/{id}/result` | `GET /internal/tutor/analyses/{id}/result` | `X-User-Id` del JWT |

- Variable nueva: `TUTOR_URL: http://tutor-component:${TUTOR_PORT}`.
- El gateway debe **añadir** `X-User-Id` (nunca aceptarlo del cliente) después
  de validar la cookie y reenviar el cuerpo tal cual.
- `DELETE /internal/tutor/users/{userId}` lo llama Auth por el gateway interno,
  sin JWT de usuario. No se publica hacia el exterior.
- El gateway ya preserva los errores estructurados con
  `_error_payload_for_upstream`. Debe mantener ese comportamiento para que el
  frontend reciba `GAME_NOT_ANALYZABLE`, `ANALYSIS_NOT_FOUND`,
  `ANALYSIS_NOT_READY`, etc. Solo los errores no estructurados se mapean por
  código HTTP.

El frontend consume `POST /api/tutor/analyses` (Vike quita `/api`) → gateway
`/tutor/analyses` → Tutor `/internal/tutor/analyses`. El polling de la sección 6
funciona contra `GET /api/tutor/analyses/{id}` y el reintento se ofrece solo si
`retryable` es `true`.

## Fuera de alcance de esta entrega

- Implementación del Analysis Worker (otro componente) y del GameState con
  `visibility` / `participants` en Game Logic (otro componente).
- Proveedor real de LLM (`LLM_API_KEY`).
- Validación con MongoDB y RabbitMQ reales, pruebas de concurrencia sobre
  infraestructura y `docker build`: aplazadas por decisión del equipo.
