# Botcito — Kevin Rojas

Servicio sin estado de ajedrez: recibe una posición FEN y un nivel de dificultad,
consulta Stockfish y devuelve una jugada legal con su notación SAN y evaluación.
No crea partidas ni persiste movimientos; esas responsabilidades permanecen en
Single Player y Game Logic.


## Arquitectura actual: Botcito-juego y Botcito-análisis

Botcito utiliza Python 3.12, FastAPI y Stockfish 15.1.

Una misma imagen Docker permite ejecutar dos servicios independientes,
cada uno con su propio pool de motores Stockfish.

### Botcito-juego

- Rol: `ENGINE_ROLE=game`
- Puerto: `8086`
- Endpoint: `POST /internal/engine/best-move`
- Consumidor: Single Player, mediante el gateway interno.
- Objetivo: calcular una jugada según el nivel de dificultad.

Solicitud:

```json
{
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "botLevel": 10
}
```

Respuesta de ejemplo:

```json
{
  "uci": "g1f3",
  "san": "Nf3",
  "evaluation": {
    "type": "cp",
    "value": 28,
    "perspective": "side_to_move"
  }
}
```

### Botcito-análisis

- Rol: `ENGINE_ROLE=analysis`
- Puerto: `8091`
- Endpoint: `POST /internal/engine-analysis/evaluate`
- Consumidor: Analysis Worker, mediante el gateway interno.
- Objetivo: evaluar una posición a la profundidad solicitada.

Solicitud:

```json
{
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "depth": 8
}
```

Respuesta de ejemplo:

```json
{
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQkBNR w KQkq - 0 1",
  "evaluation": {
    "type": "cp",
    "value": 26,
    "perspective": "white"
  },
  "bestMove": {
    "uci": "g1f3",
    "san": "Nf3"
  },
  "depth": 8
}
```

La profundidad máxima es configurable mediante `ANALYSIS_DEPTH_MAX`,
con valor predeterminado de 18.

Las posiciones terminales se evalúan sin consultar Stockfish:

- Jaque mate a favor de blancas: `100000` centipeones.
- Jaque mate a favor de negras: `-100000` centipeones.
- Ahogado o tablas: `0` centipeones.

En estos casos, `bestMove` es `null`.

### Configuración de los contenedores

| Variable | Juego | Análisis |
|---|---|---|
| PORT | 8086 | 8091 |
| ENGINE_ROLE | game | analysis |
| ENGINE_POOL_SIZE | 2 | 2 |
| ENGINE_THREADS | 1 | 1 |
| ENGINE_TIMEOUT_MS | 2000 | 10000 |

Ambos servicios ofrecen `GET /health`.

Los endpoints `/internal/*` están destinados a la comunicación
entre servicios mediante el gateway interno, no a exposición pública.

Las rutas antiguas `/engine/best-move` y `/best-move` se conservan
temporalmente por compatibilidad hasta completar la migración
de Single Player y el gateway.


## Arranque independiente con Docker Compose

Botcito-juego y Botcito-análisis pueden ejecutarse mediante un único
archivo Docker Compose, utilizando la misma imagen con Stockfish 15.1.

Cada servicio tiene su propio contenedor, pool de motores y configuración.

### Iniciar ambos servicios

Desde la raíz del repositorio:

```bash
docker compose -f Backend/botcito-component/compose.yaml up -d --build
```

Los servicios disponibles son:

| Servicio | Rol | Puerto |
|---|---|---|
| botcito | game | 8086 |
| botcito-analysis | analysis | 8091 |

Los puertos se publican únicamente en `127.0.0.1` para pruebas locales.

### Verificar el estado

```bash
docker compose -f Backend/botcito-component/compose.yaml ps
```

Ambos contenedores deben encontrarse en estado `healthy`.

Verificar los endpoints de salud:

```bash
curl http://localhost:8086/health
curl http://localhost:8091/health
```

Respuesta esperada de ambos servicios:

```json
{"status":"ok"}
```

La documentación interactiva está disponible localmente en:

- Botcito-juego: http://localhost:8086/docs
- Botcito-análisis: http://localhost:8091/docs

Los contenedores utilizan Python 3.12 y Stockfish 15.1,
instalado desde el paquete Debian `stockfish=15.1-4`.

No requieren bases de datos ni credenciales para su arranque independiente.

### Detener ambos servicios

Desde la raíz del repositorio:

```bash
docker compose -f Backend/botcito-component/compose.yaml down
```

Esto detiene y elimina los contenedores administrados por Compose,
sin eliminar el código ni las imágenes Docker.

Esta configuración corresponde al entorno independiente de desarrollo.
La integración en el Docker Compose principal del proyecto y las
comunicaciones mediante el gateway interno requieren validaciones adicionales.

## Contrato de compatibilidad (temporal)

Las rutas `/engine/best-move` y `/best-move` pertenecen al contrato
anterior de Botcito-juego y se mantienen temporalmente para conservar
la compatibilidad con los consumidores que todavía no han migrado.

El contrato vigente utiliza `POST /internal/engine/best-move`, con el
parámetro `botLevel` (1 a 20).

Los ejemplos siguientes corresponden a las rutas de compatibilidad
y pueden seguir utilizando el parámetro histórico `level`.

Estas rutas se retirarán cuando Single Player y el gateway hayan
completado la migración al contrato interno.


`POST /engine/best-move`, puerto **8086**:

```json
{
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "level": 10
}
```

Ejemplo de forma de respuesta; la jugada y el valor pueden variar:

```json
{
  "uci": "e2e4",
  "san": "e4",
  "evaluation": {"type": "cp", "value": 25}
}
```

Prueba desde Bash:

```bash
curl -X POST http://localhost:8086/engine/best-move \
  -H 'Content-Type: application/json' \
  -d '{"fen":"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1","level":10}'
```

Prueba desde PowerShell:

```powershell
$body = @{
  fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
  level = 10
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://localhost:8086/engine/best-move' -ContentType 'application/json' -Body $body
```

- `level` es un entero estricto entre **1 y 20** y configura `Skill Level` de
  Stockfish. No representa un Elo garantizado. Una sola jugada no permite medir
  la diferencia de fuerza entre niveles.
- `evaluation` evalúa **la jugada seleccionada**, desde la perspectiva del bando
  al que le toca jugar en el FEN recibido. Positivo favorece a ese bando.
- `cp` expresa centipeones; `mate` expresa distancia de mate en jugadas,
  positiva si ese bando da mate y negativa si lo recibe. Es una evaluación de
  búsqueda limitada, no una prueba exhaustiva.
- Se dedican 300 ms a elegir la jugada y 200 ms a evaluarla con fuerza completa.
  El tiempo total incluye comunicación y preparación del motor.
- La API exige seis campos FEN y valida la consistencia de la posición.
  Un FEN no contiene el historial necesario para detectar repetición triple;
  Game Logic decide si la partida ya terminó por otras reglas.

## Compatibilidad e integración

El cliente actual `Backend/GameService/.../BotcitoClient.java` pide
`POST /best-move` y lee el campo `move`. La ruta de compatibilidad devuelve los
mismos campos del contrato y añade `move` con el mismo valor que `uci`.

| Consumidor | Configuración | Ruta |
|---|---|---|
| Single Player en Compose principal | `BOTCITO_URL=http://botcito-component:8086` | `/best-move` |
| Single Player en Compose de desarrollo | `BOTCITO_URL=http://botcito:8086` | `/best-move` |
| Single Player ejecutado en el host | `BOTCITO_URL=http://localhost:8086` | `/best-move` |
| API Gateway | `BOTCITO_SERVICE_URL=http://botcito-component:8086` | `/engine/best-move` |

El Gateway expone `POST /engine/best-move` y conserva el JSON y el estado HTTP
de Botcito. Su espera máxima es de 10 segundos. El Java actual sigue usando
la conexión directa y la ruta de compatibilidad. Para cumplir estrictamente el
recorrido Single Player → Gateway → Botcito del documento de arquitectura,
el integrador deberá migrar el cliente Java a la ruta canónica y al campo `uci`;
no basta con apuntar su URL actual al Gateway.

El Compose principal registra `botcito-component` y espera a que esté saludable
antes de iniciar Single Player. Las rutas de Frontend, del Dockerfile del Gateway
y de Databases se corrigieron para respetar mayúsculas/minúsculas en Linux.
El `.env` del proyecto completo sigue necesitando la configuración de Infra;
el puerto externo nuevo es `BOTCITO_PORT=8086` (internamente siempre 8086).
No ejecutar simultáneamente los Compose independiente, de desarrollo y principal
sobre el mismo puerto del host.

## Errores y capacidad

Todos los errores propios del servicio tienen esta forma:

```json
{"error":{"code":"INVALID_FEN","message":"La posición FEN no es válida."}}
```

| HTTP | Código | Motivo |
|---|---|---|
| 400 | `VALIDATION_ERROR` | JSON/campos/tipos/nivel inválidos |
| 400 | `INVALID_FEN` | FEN mal formado o posición inconsistente |
| 422 | `NO_LEGAL_MOVES` | Jaque mate o ahogado |
| 503 | `ENGINE_BUSY` | Todos los motores del pool están ocupados; no se mantienen solicitudes en cola |
| 503 | `SERVICES_UNAVAILABLE` | Motor no disponible o fallo del proceso Stockfish |
| 504 | `ENGINE_TIMEOUT` | El motor superó el tiempo máximo de ejecución configurado |



Cada contenedor dispone de un pool independiente de procesos Stockfish,
configurado mediante `ENGINE_POOL_SIZE`, `ENGINE_THREADS` y
`ENGINE_TIMEOUT_MS`.

La configuración actual utiliza dos motores por contenedor, con un hilo
y 32 MB de hash por motor.

Cada proceso atiende una solicitud a la vez. Cuando todos los motores
del pool están ocupados, el servicio responde `503 ENGINE_BUSY` sin
mantener una cola de espera.

Si un motor falla, se descarta únicamente ese proceso y se intenta
reiniciarlo en una solicitud posterior. Los demás motores pueden
continuar atendiendo peticiones.

Botcito-juego utiliza un timeout de 2000 ms y Botcito-análisis uno de
10000 ms, según la configuración de cada contenedor.


El endpoint `/health` responde correctamente mientras exista al menos
un motor operativo en el pool. Si todos los motores están fuera de
servicio, responde `503 SERVICES_UNAVAILABLE`.

Los motores que fallen se intentan recuperar individualmente.
Si el binario Stockfish no está disponible durante el arranque,
la aplicación falla explícitamente.

Stockfish dispone de hasta 30 segundos para inicializarse al arrancar la API,
y 5 segundos para reiniciarse durante una solicitud. Después de inicializarlo,
la espera de comandos UCI vuelve a 2 segundos (más el tiempo de búsqueda cuando
corresponde). Esto permite el arranque conjunto con los otros contenedores sin
alargar innecesariamente las consultas normales.

## Desarrollo local sin Docker

Requiere Python 3.12 y un ejecutable Stockfish compatible con el sistema.
En Debian/Ubuntu se puede instalar con `sudo apt-get install stockfish`.
También se puede obtener desde <https://stockfishchess.org/download/>.

```bash
cd Backend/botcito-component
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export STOCKFISH_PATH=/usr/games/stockfish
uvicorn main:app --host 0.0.0.0 --port 8086
```

En PowerShell, usar `.\.venv\Scripts\Activate.ps1` y definir
`$env:STOCKFISH_PATH = 'C:\ruta\stockfish.exe'` en lugar de los dos comandos Bash
equivalentes. No es necesario activar el entorno si se invocan sus ejecutables
por su ruta completa.

## Pruebas

Con el entorno anterior y `STOCKFISH_PATH` configurado:

```bash
python -m pytest -q
```

Las pruebas usan Stockfish real y verifican el contrato, jugadas de ambos bandos
en niveles 1/10/20, promoción, SAN, evaluación de mate para ambos colores,
validación, mate/ahogado, compatibilidad Java, saturación, reinicio del motor y un arranque retrasado 3 segundos.
No comparan aperturas concretas porque la selección puede variar.

Las pruebas del proxy se ejecutan en un entorno separado, desde
`Backend/api-gateway`, instalando su `requirements-dev.txt` y ejecutando
`python -m pytest -q`. Comprueban propagación de respuestas y errores de conexión
con transporte HTTP simulado.

Validación de esta entrega (12 de octubre de 2026, base `5c3b806`): **30 pruebas
de Botcito aprobadas** con Python 3.12 y Stockfish 17.1 compilado desde su fuente
oficial, y **6 pruebas del Gateway aprobadas** con sus dependencias propias.
También se verificaron la sintaxis YAML, las rutas de los Dockerfiles y las
referencias entre servicios. Docker y la partida completa con Java/Frontend
no se ejecutaron en este entorno; el binario de Debian incluido por el Dockerfile
puede tener una versión distinta del usado en las pruebas locales.

La validación histórica con Stockfish 17.1 corresponde al prototipo
anterior y no representa la versión normativa de esta implementación.

### Validación actual — 3 de noviembre de 2026

La implementación actual de Botcito utiliza Python 3.12 y Stockfish 15.1,
instalado en Docker mediante el paquete Debian `stockfish=15.1-4`.

La misma imagen Docker permite ejecutar dos servicios independientes:

- **Botcito-juego:** puerto 8086, `ENGINE_ROLE=game`.
- **Botcito-análisis:** puerto 8091, `ENGINE_ROLE=analysis`.

Ambos servicios utilizan un pool configurable de procesos Stockfish,
con dos motores y un hilo por motor en la configuración probada.

Resultados de validación:

- 41 pruebas automatizadas aprobadas mediante Pytest.
- Ambos contenedores ejecutándose correctamente en Docker.
- Healthchecks satisfactorios en los puertos 8086 y 8091.
- Evaluaciones reales verificadas mediante solicitudes HTTP.
- Validación de aislamiento de endpoints y rechazo de solicitudes inválidas.

Commit de referencia: `3b1f0b4`, rama `botcito`.



La prueba HTTP local con dos servidores Uvicorn y Stockfish real también pasó:
Gateway → Botcito respondió `200` con `f7g7`, `Qg7#` y mate en 1; un FEN inválido
conservó el `400 INVALID_FEN`, y `/best-move` devolvió `move` igual a `uci`.

## Integración verificada en el equipo de Kevin

El 12 de octubre de 2026, después de ampliar el tiempo de inicialización del motor,
las capturas compartidas por Kevin confirmaron los cuatro contenedores en ejecución
y Botcito saludable. La página `tools/prueba-integracion.html`, abierta localmente,
completó el flujo de desarrollo en `ws://localhost:8083/ws/game`:

1. Creación de partida BOT, nivel 10, humano con blancas: `game_created`.
2. Movimiento humano `e2e4`: `game_state`, turno BLACK.
3. Respuesta de Botcito `c7c6`: `game_state`, turno WHITE, FEN actualizado.
4. Abandono de prueba: `game_over`, BLACK_WINS, RESIGNATION.

Esto verifica ese flujo Single Player → Botcito y la aplicación de los movimientos
con Game Logic en el entorno del usuario. El mensaje de cierre se envía antes de
completar el guardado del resultado: estas capturas no comprueban por sí solas la
persistencia final en MongoDB. Tampoco prueban el frontend general, el Gateway en
ese equipo ni partidas simultáneas.

Para repetirlo, arrancar el Compose de desarrollo y abrir
`tools/prueba-integracion.html` en un navegador del mismo computador. Pulsar
**Probar integración**. Cada ejecución crea y termina una partida de prueba.

## Dependencias

`chess` es el paquete de implementación de python-chess. Stockfish y python-chess
son proyectos externos bajo GPL; conservar sus avisos y obligaciones al
redistribuirlos. El repositorio no incluye binarios del motor.

- <https://python-chess.readthedocs.io/en/stable/engine.html>
- <https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html>
