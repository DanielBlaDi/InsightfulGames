# Botcito — Kevin Rojas

Servicio sin estado de ajedrez: recibe una posición FEN y un nivel de dificultad,
consulta Stockfish y devuelve una jugada legal con su notación SAN y evaluación.
No crea partidas ni persiste movimientos; esas responsabilidades permanecen en
Single Player y Game Logic.

## Arranque independiente con Docker

Desde la raíz del repositorio:

```bash
docker compose -f Backend/botcito-component/compose.yaml up --build -d
curl http://localhost:8086/health
```

Respuesta esperada: `{"status":"ok"}`. La documentación interactiva está en
<http://localhost:8086/docs>. El contenedor instala Stockfish desde Debian,
ejecuta la API con Python 3.12 y un usuario sin privilegios, y comprueba su salud.
No necesita base de datos, credenciales ni archivo `.env` para este arranque.

Para detenerlo:

```bash
docker compose -f Backend/botcito-component/compose.yaml down
```

## Contrato principal

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
| 503 | `ENGINE_BUSY` | Otra consulta ocupa el proceso del motor |
| 503 | `ENGINE_UNAVAILABLE` | Motor terminado, fallo UCI o conexión del Gateway fallida |

Hay un proceso Stockfish por worker, con un hilo y 32 MB de hash. No se mezclan
consultas UCI ni se crea una cola ilimitada. El despliegue inicial atiende una
consulta a la vez: el consumidor debe manejar/reintentar `ENGINE_BUSY` con espera
acotada. El cliente Java actual propaga los errores y aún no implementa ese
reintento; la prueba integrada con partidas simultáneas queda pendiente.

Si Stockfish termina, `/health` responde 503 y la siguiente solicitud de jugada
intenta reiniciarlo. Si el binario falta al arrancar, la aplicación falla
explícitamente. No se sustituye el motor por respuestas simuladas.

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
