# Analysis Worker (`analysis-worker`)

Componente en segundo plano del Prototipo 2. Implementa la **sección 17** del
contrato vigente (`Documentación/CONTRATO_TECNICO_DEFINITIVO.docx.md`): consume
las solicitudes de análisis del Tutor, pide los datos de la partida a Game
Logic, evalúa las posiciones con Botcito-análisis, calcula el resultado y lo
escribe de forma condicionada en MongoDB de análisis.

- Puerto: **8089** (`PORT`).
- Rutas: solo `GET /health`. Las rutas automáticas de documentación están
  desactivadas.
- Base: MongoDB de análisis. Es la única excepción aceptada a la regla de que
  ningún servicio escribe en la base de otro: solo actualiza los campos
  acotados del documento de análisis.
- Mensajería: consume `tutor.analysis.requested` desde
  `analysis-worker.requested`; no publica eventos de dominio.
- Concurrencia: un análisis a la vez por proceso. Varias instancias son
  seguras gracias al reclamo atómico.

## Estado

Implementado y probado con dobles en memoria:

```text
97 passed, 1 skipped
```

La prueba omitida es la integración con MongoDB real
(`tests/test_integration_mongo.py`), que solo corre si existe
`MONGO_TEST_URL`. Están pendientes, por falta de Docker en el entorno:

- validación con MongoDB y RabbitMQ reales;
- prueba extremo a extremo con Tutor, Game Logic y Botcito-análisis;
- `docker build` y despliegue en Compose.

## Desviación respecto de las tareas del contrato

El apartado 17.1 del contrato define **Python 3.12**, pero varias tareas del
mismo apartado piden un módulo Go 1.24. La decisión de este repositorio es
**Python 3.12**, tomada explícitamente para este componente. Se conservan la
carpeta `Backend/analysis-worker/`, el puerto 8089, el Dockerfile propio y el
contrato funcional de la sección 17.

La imagen base es `python:3.12-slim-bookworm`. En el entorno local las pruebas
se ejecutaron con un intérprete Python 3.14 porque era el disponible; el código
no usa características exclusivas de 3.14.

## Ciclo de un análisis

1. El worker recibe `tutor.analysis.requested` por RabbitMQ o encuentra el
   análisis por polling.
2. Reclama el documento de forma atómica con `$$NOW`. Si no puede, otro proceso
   lo tiene: hace `ack` sin trabajo.
3. Arranca la renovación del lease cada `ANALYSIS_STALE_MINUTES / 3`.
4. Pide `GET /internal/logic/games/{id}/analysis-input` por el gateway interno.
5. Reconstruye las `N+1` posiciones con `python-chess` a partir de
   `initialFen` y las jugadas UCI.
6. Evalúa cada posición con
   `POST /internal/engine-analysis/evaluate`, una petición en vuelo a la vez,
   con la `depth` del análisis.
7. Calcula `cpLoss`, clasificación y resumen por color.
8. Escribe `result` y pasa a `completed`, condicionado por dueño y lease
   vigente. Si el lease venció, descarta el resultado y hace `ack`.
9. Ante un fallo clasificado, escribe `failed` y `failureKind`, y hace `ack`.
   Un análisis `failed` no se reintenta por el broker; el Tutor decide si lo
   reactiva.

## Evento consumido

Exchange `tutor.events` (topic, durable), routing key
`tutor.analysis.requested`:

```json
{
  "eventId": "uuid",
  "eventType": "tutor.analysis.requested",
  "occurredAt": "2026-10-29T15:25:00Z",
  "analysisId": "uuid",
  "gameId": "uuid",
  "requestedBy": "uuid",
  "language": "es",
  "detailLevel": "standard",
  "depth": 15
}
```

El worker valida `eventId`, `analysisId`, `gameId`, `eventType` y `depth`
(entero entre 1 y `ANALYSIS_DEPTH_MAX`). Un mensaje inválido va directo a
`.dlq` para no bloquear la cola.

La idempotencia es por `analysisId`: un mensaje duplicado sobre un análisis
`completed`, `failed` o ya reclamado se confirma sin volver a calcularlo.

## Topología RabbitMQ

| Elemento | Valor |
| :--- | :--- |
| Exchange de entrada | `tutor.events` (topic, durable) |
| Routing key | `tutor.analysis.requested` |
| Cola principal | `analysis-worker.requested` (durable) |
| Cola de espera | `analysis-worker.requested.wait` |
| Argumentos de `.wait` | `x-message-ttl=5000`, `x-dead-letter-exchange=""`, `x-dead-letter-routing-key=analysis-worker.requested` |
| Exchange de reintentos | `retry.events` (direct, durable) |
| Binding de `.wait` | `retry.events` con routing key `analysis-worker.requested` |
| Cola de descarte | `analysis-worker.requested.dlq` (durable) |
| Prefetch | `1` |
| Mensajes | persistentes |

### Reintentos del broker

- Seis intentos totales: uno inicial y cinco reintentos.
- Al fallar por infraestructura, se publica en `retry.events` con
  `x-retry-count + 1` y se hace `ack` del mensaje original.
- Con `x-retry-count` en 5, el mensaje va a `.dlq`.
- Si el reenvío falla, se rechaza con `requeue`.
- Un mensaje inválido va directo a `.dlq`.
- `.dlq` se revisa a mano; no hay reprocesamiento automático.

Los fallos de infraestructura incluyen MongoDB, errores inesperados y cualquier
excepción no clasificada. Los fallos de negocio ya se persisten como `failed`
antes de confirmar el mensaje, por lo que no entran en este ciclo.

## Reclamo, lease y recuperación

Todas las operaciones sensibles al tiempo usan `$$NOW` de MongoDB.

### Reclamo

Una sola actualización por `analysisId`, condicionada a:

- `status: pending`, o
- `status: processing` con `leaseUntil` vencido.

Si reclama, fija `status: processing`, `leaseOwner`, `leaseUntil = ahora +
ANALYSIS_STALE_MINUTES` y `claimCount + 1`. No reclama si `claimCount` ya
alcanzó `ANALYSIS_MAX_RETRIES`.

### Renovación

Cada `ANALYSIS_STALE_MINUTES / 3`, condicionada por `analysisId`, `status:
processing` y `leaseOwner`. Si no modifica nada, el worker perdió el lease y
aborta el trabajo en curso.

### Escritura final

Condicionada por `analysisId`, `status: processing`, `leaseOwner` y
`leaseUntil > $$NOW`. Si el lease venció, el resultado se descarta y se hace
`ack`; un worker atrasado nunca sobrescribe a otro.

### Recuperación por polling

Cada `POLL_INTERVAL_SECONDS`:

- busca `pending` con más de `ANALYSIS_STALE_MINUTES` de antigüedad;
- busca `processing` con `leaseUntil` vencido;
- procesa hasta **10** por ciclo, en secuencia;
- si un análisis alcanzó `ANALYSIS_MAX_RETRIES` reclamos, lo pasa a `failed`
  con `failureKind: transient`.

El polling es la red de seguridad cuando RabbitMQ no está disponible o cuando
el Tutor no pudo publicar.

## Cálculo

### Posiciones y evaluaciones

- `N` jugadas producen `N+1` posiciones: la inicial y la que queda tras cada
  jugada.
- Cada posición se evalúa una vez, desde blancas, con la `depth` del evento.
- `cp`: centésima de peón, positiva a favor de blancas.

### Mate y posiciones terminales

- Mate no terminal: `MATE_SCORE = 100000`.
  - `N > 0`: `100000 - N`.
  - `N < 0`: `-(100000 - |N|)`.
- Terminal: Botcito-análisis ya entrega centipeones:
  - `100000` si ganan blancas;
  - `-100000` si ganan negras;
  - `0` en ahogado o tablas;
  - `bestMove: null`.

### cpLoss

- Blancas: `max(0, E_antes - E_después)`.
- Negras: `max(0, E_después - E_antes)`.

### Clasificación, por prioridad

| Clasificación | Condición |
| :--- | :--- |
| `best` | La jugada es `bestMove.uci` de `E_antes` |
| `blunder` | `cpLoss >= ANALYSIS_BLUNDER_CP` |
| `mistake` | `cpLoss >= ANALYSIS_MISTAKE_CP` |
| `inaccuracy` | `cpLoss >= ANALYSIS_INACCURACY_CP` |
| `good` | El resto |

Umbrales por defecto: 50, 100 y 300 centipeones.

### Resumen

Por cada color se guardan los conteos de las cinco clasificaciones y
`averageCpLoss`. El promedio excluye jugadas cuya `E_antes` o `E_después` vino
de un mate o de una posición terminal con mate. Si no hay jugadas elegibles,
`averageCpLoss` es `null`, nunca `0`. El promedio se redondea a un decimal.

### Forma de `result`

```json
{
  "summary": {
    "white": {
      "best": 0,
      "good": 0,
      "inaccuracy": 1,
      "mistake": 0,
      "blunder": 0,
      "averageCpLoss": 80.0
    },
    "black": {
      "best": 1,
      "good": 0,
      "inaccuracy": 0,
      "mistake": 0,
      "blunder": 0,
      "averageCpLoss": 20.0
    }
  },
  "moves": [
    {
      "ply": 1,
      "color": "white",
      "uci": "e2e4",
      "san": "e4",
      "bestMove": { "uci": "e2e4", "san": "e4" },
      "evalBefore": 100,
      "evalAfter": 20,
      "cpLoss": 80,
      "classification": "inaccuracy"
    }
  ]
}
```

## Clasificación de fallos

| Caso | `failureKind` | Efecto |
| :--- | :--- | :--- |
| Motor ocupado (`ENGINE_BUSY`), timeout de motor (`ENGINE_TIMEOUT`), 5xx, red | `transient` | Se reintenta por evaluación; agotados los intentos, `failed` y `ack` |
| Game Logic caído o 5xx al pedir `analysis-input` | `transient` | `failed` y `ack`; el Tutor puede reactivar |
| `analysis-input` 404 o 409, FEN inválida, jugada ilegal, datos incoherentes | `permanent` | `failed` y `ack`; no se reintenta |
| Evaluación 400 (`VALIDATION_ERROR`, `INVALID_FEN`) | `permanent` | `failed` y `ack` |
| Fallo de MongoDB o error inesperado | — | No se confirma: reintento por broker o recuperación por polling |

Reintentos por evaluación: hasta `ANALYSIS_MAX_RETRIES` intentos totales, con
pausas de 1, 2, 4 y 8 segundos (la última se repite si hay más intentos).

Los fallos transitorios de `analysis-input` **no** se reintentan dentro del
worker: se marcan `failed` con `failureKind: transient` y el Tutor decide si
publica una reactivación. Solo las evaluaciones del motor tienen reintento
inmediato dentro del mismo intento.

## Persistencia

El worker escribe únicamente en `analyses`:

- `result`, `failureKind`, `startedAt`, `completedAt`, `leaseUntil`,
  `leaseOwner`, `claimCount`;
- y `status`, `error`, `updatedAt` en las transiciones previstas.

No modifica `analysisId`, `gameId`, `engineVersion`, `language`,
`detailLevel`, `depth`, `requestedBy`, `participantIds`, `explanation`,
`createdAt` ni `reactivations`, que pertenecen al Tutor.

En la transición final se eliminan `leaseUntil` y `leaseOwner`; `claimCount`
se conserva para diagnóstico. Si el documento fue borrado por la saga de
cuenta, la escritura no encuentra nada y el resultado se descarta.

## Configuración

| Variable | Valor por defecto | Uso |
| :--- | :--- | :--- |
| `PORT` | `8089` | Puerto HTTP |
| `LOG_LEVEL` | `INFO` | Nivel de logs |
| `GATEWAY_INTERNAL_URL` | `http://api-gateway-component:8080` | Base de las llamadas internas |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | Conexión al broker |
| `MONGO_ANALYSIS_URL` | `mongodb://localhost:27017` | Conexión a MongoDB de análisis |
| `MONGO_ANALYSIS_DATABASE` | `insightful_analysis` | Base de análisis |
| `ANALYSIS_DEPTH_MAX` | `18` | Tope de profundidad aceptada |
| `ANALYSIS_MAX_RETRIES` | `5` | Intentos por evaluación y límite de reclamos |
| `ANALYSIS_INACCURACY_CP` | `50` | Umbral de imprecisión |
| `ANALYSIS_MISTAKE_CP` | `100` | Umbral de error |
| `ANALYSIS_BLUNDER_CP` | `300` | Umbral de error grave |
| `POLL_INTERVAL_SECONDS` | `5` | Intervalo del polling |
| `ANALYSIS_STALE_MINUTES` | `5` | Vigencia del lease |
| `HTTP_TIMEOUT` | `15` | Timeout de las llamadas internas |
| `WORKER_ID` | hostname:pid:aleatorio | Identidad del `leaseOwner` |

`ANALYSIS_MAX_RETRIES` mantiene el doble significado que el contrato deja
pendiente de validación: intentos por evaluación y límite de reclamos. Los
reintentos internos del broker son siempre seis intentos totales, según la
sección 19.4.

## Salud

`GET /health` responde `200 {"status": "ok"}` si MongoDB responde a una lectura
mínima y `503 SERVICES_UNAVAILABLE` si no. No consulta RabbitMQ ni Game Logic.
La comprobación es *fail-closed*: cualquier excepción también produce 503.

## Estructura

```text
Backend/analysis-worker/
├── app/
│   ├── broker.py        # topología y publicación de reintentos/DLQ
│   ├── calculation.py   # reconstrucción, mate, cpLoss y resumen
│   ├── config.py        # variables de entorno y constantes del contrato
│   ├── consumer.py      # consumo con reconexión
│   ├── db.py            # cliente MongoDB
│   ├── engine.py        # cliente de Botcito-análisis
│   ├── errors.py        # fallos clasificados y errores internos
│   ├── game_logic.py    # cliente de analysis-input
│   ├── http_utils.py    # lectura del código de error común
│   ├── messaging.py     # política ack/reintento/DLQ
│   ├── models.py        # evento, jugadas y evaluaciones
│   ├── poller.py        # recuperación de análisis perdidos
│   ├── processor.py     # reclamo, lease, evaluación y escritura final
│   ├── repository.py    # pipelines atómicos con $$NOW
│   └── timeutils.py     # fechas ISO 8601 UTC
├── tests/
│   ├── conftest.py                    # repositorio falso atómico y dobles
│   ├── test_broker.py                 # topología y publicación de reintentos
│   ├── test_calculation.py
│   ├── test_clients.py
│   ├── test_config.py
│   ├── test_health.py
│   ├── test_integration_mongo.py      # opcional, requiere MONGO_TEST_URL
│   ├── test_messaging.py
│   ├── test_poller.py
│   └── test_processor.py
├── Dockerfile
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

`requirements.txt` fija `python-chess==1.999`, que instala el módulo `chess`
1.11.2. Ese es el nombre y la versión reales publicados en PyPI.

## Pruebas

Las pruebas usan un `FakeAnalysisRepository` atómico con reloj simulado, porque
`mongomock` no ejecuta pipelines con `$$NOW`. Cubren:

- cálculo de `cpLoss`, mate, clasificación, promedio y `averageCpLoss: null`;
- reconstrucción de posiciones con FEN inválida o jugadas ilegales;
- reclamo, renovación, escritura condicionada y carreras de dos workers;
- recuperación por polling, lote de 10 y límite de reclamos;
- clasificación de fallos y reintentos por evaluación;
- topología RabbitMQ, bindings, argumentos de `.wait` y publicación a
  reintentos/DLQ;
- política `ack`/reintento/DLQ del broker;
- clientes HTTP y sus códigos de error;
- configuración, defaults y validaciones;
- `/health` y ausencia de rutas adicionales.

Ejecutar la suite:

```powershell
cd Backend/analysis-worker
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Integración opcional con MongoDB real:

```powershell
$env:MONGO_TEST_URL = "mongodb://localhost:27017"
$env:MONGO_TEST_DATABASE = "analysis_worker_test"
python -m pytest -q tests/test_integration_mongo.py
```

La prueba crea una colección temporal, ejecuta reclamo, renovación, escritura
final y descarte de un worker ajeno, y la elimina al terminar. No debe apuntar a
una base con datos reales.

## Docker

```powershell
docker build -t analysis-worker Backend/analysis-worker
docker run --rm -p 8089:8089 `
  -e MONGO_ANALYSIS_URL=mongodb://host.docker.internal:27017 `
  -e RABBITMQ_URL=amqp://guest:guest@host.docker.internal:5672/ `
  analysis-worker
```

El contenedor corre como usuario `10001:10001`, escucha en `0.0.0.0:8089` y su
healthcheck usa `/health`.

## Handoff pendiente (fuera de este componente)

Este repositorio solo modifica `Backend/analysis-worker/`. Para que el flujo
funcione de extremo a extremo, otras tareas deben completar:

1. **Game Logic**: `GET /internal/logic/games/{id}/analysis-input` con
   `{ gameId, initialFen, status, result, moves }`, incluido `409
   GAME_NOT_FINISHED`.
2. **Botcito-análisis**: `POST /internal/engine-analysis/evaluate` con
   perspectiva blancas, `depth` obligatoria, detección previa de posiciones
   terminales y los errores `ENGINE_BUSY`, `ENGINE_TIMEOUT`,
   `SERVICES_UNAVAILABLE`, `INVALID_FEN` y `VALIDATION_ERROR`.
3. **Gateway web**: proxies internos para ambas rutas, sin exponerlas fuera de
   la red `app`.
4. **Compose**: servicio `analysis-worker` con puerto 8089, variables de la
   tabla anterior, dependencia de MongoDB/RabbitMQ y healthcheck.
5. **`.env.example`**: las variables nuevas, en particular
   `ANALYSIS_MAX_RETRIES`, `ANALYSIS_STALE_MINUTES`,
   `POLL_INTERVAL_SECONDS` y los umbrales.
6. **Prueba E2E**: crear análisis en Tutor, verificar consumo, evaluación,
   resultado en MongoDB y entrega por Tutor, con dos workers y recuperación de
   lease.

Mientras esas piezas no existan, el worker puede arrancar y responder
`/health`, pero un análisis real terminará en `failed` al no encontrar las
rutas internas.
