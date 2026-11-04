# Verificación del sistema completo con Docker

Para quien tenga Docker Desktop. Prueba la rama `fix/full-stack-startup` con todos los servicios
reales y devuelve los resultados (sección 8) para corregir lo que falle. Tiempo estimado: 30–45 min
(la primera construcción de imágenes es la parte lenta).

> **No borrar datos.** No uses `docker compose down -v`, `docker volume rm` ni `docker system prune`:
> borran las bases de datos. Para parar: `docker compose stop` o `docker compose down` (sin `-v`).

Los comandos son de PowerShell (Windows). En Git Bash, macOS o Linux funcionan igual salvo el
bloque del `.env`, que tiene versión bash.

## 0. Preparar la rama

```powershell
git fetch origin
git switch fix/full-stack-startup      # o: git switch -c fix/full-stack-startup origin/fix/full-stack-startup
git pull --ff-only
```

## 1. Crear `.env` sin exponer secretos

`.env` está en `.gitignore`: nunca se sube. Si ya tienes un `.env`, **no lo sobrescribas** (sus
contraseñas son las que ya usan tus volúmenes de MySQL, MongoDB y PostgreSQL). Si no lo tienes,
este bloque lo crea a partir de `.env.example` con secretos aleatorios y **no los muestra**:

```powershell
if (Test-Path .env) { 'Ya existe .env: no se toca' } else {
  function New-Secret { $b = New-Object byte[] 36; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [Convert]::ToBase64String($b).Replace('+','-').Replace('/','_').TrimEnd('=') }
  $v = @{
    FRONTEND_PORT='80'; MOBILE_GATEWAY_PORT='8090'; LOG_LEVEL='INFO'; HTTP_TIMEOUT='15'
    JWT_SECRET=(New-Secret)+(New-Secret); JWT_ALGORITHM='HS256'; COOKIE_SECURE='false'; WS_ALLOWED_ORIGINS='http://localhost'
    MYSQL_DATABASE='insightful_auth'; MYSQL_USER='auth_app'; MYSQL_PASSWORD=(New-Secret); MYSQL_ROOT_PASSWORD=(New-Secret); OUTBOX_RELAY_INTERVAL_MS='2000'
    MONGO_DATABASE='games'; MONGO_USER='games_app'; MONGO_PASSWORD=(New-Secret); WAITING_TIMEOUT_MINUTES='30'
    MONGO_ROOT_USERNAME='root'; MONGO_ROOT_PASSWORD=(New-Secret)
    POSTGRES_DB='insightful_profile'; POSTGRES_USER='profile_app'; POSTGRES_PASSWORD=(New-Secret)
    MONGO_ANALYSIS_DATABASE='insightful_analysis'; MONGO_ANALYSIS_USER='analysis_app'; MONGO_ANALYSIS_PASSWORD=(New-Secret)
    RABBITMQ_DEFAULT_USER='insightful'; RABBITMQ_DEFAULT_PASS=(New-Secret)
    ENGINE_VERSION='stockfish-15.1'; ANALYSIS_DEPTH_DEFAULT='12'; ANALYSIS_DEPTH_MAX='18'; ANALYSIS_MAX_REACTIVATIONS='3'; LLM_PROVIDER='mock'
    RECONNECT_WINDOW_SECONDS='60'; ANALYSIS_MAX_RETRIES='3'; ANALYSIS_INACCURACY_CP='50'; ANALYSIS_MISTAKE_CP='100'; ANALYSIS_BLUNDER_CP='300'
    POLL_INTERVAL_SECONDS='30'; ANALYSIS_STALE_MINUTES='10'; TIMEOUT_POLL_INTERVAL_SECONDS='5'; TIMEOUT_BATCH_LIMIT='50'
  }
  $lines = (Get-Content .env.example) | ForEach-Object { if ($_ -match '^([A-Z_]+)=$' -and $v.ContainsKey($Matches[1])) { "$($Matches[1])=$($v[$Matches[1]])" } else { $_ } }
  [IO.File]::WriteAllLines((Join-Path $PWD '.env'), [string[]]$lines, (New-Object Text.UTF8Encoding $false))   # UTF-8 sin BOM
  'Creado .env. Variables vacías:'; Select-String -Path .env -Pattern '^[A-Z_]+=$' | ForEach-Object { $_.Line }
}
```

Versión bash: `cp .env.example .env` y rellena cada línea vacía; para los secretos usa
`openssl rand -base64 36`.

**Valores que importan:**

- `WS_ALLOWED_ORIGINS` debe ser exactamente la URL del navegador: `http://localhost` si
  `FRONTEND_PORT=80`, o `http://localhost:<puerto>` si cambias el puerto. Si no coincide, el
  ajedrez se conecta pero el WebSocket se cierra con 4403.
- Si el puerto 80 está ocupado, usa `FRONTEND_PORT=3000` y `WS_ALLOWED_ORIGINS=http://localhost:3000`.
- `JWT_SECRET` debe tener al menos 32 bytes (el generador da ~96 caracteres).

Para compartir la configuración, comparte **solo los nombres**: `Select-String -Path .env -Pattern '^([A-Z_]+)=' | % { $_.Matches[0].Groups[1].Value }`.

## 2. Validar y levantar

```powershell
docker compose config --quiet; "config: exit $LASTEXITCODE"     # 0 = sin errores (no imprime secretos)
docker compose up --build -d
docker compose ps -a
```

Espera 2–3 minutos y repite `docker compose ps -a` hasta que todo esté `running` o `healthy`.
Deben quedar `healthy`: `mongo-db`, `mongo-analysis-db`, `mysql-db`, `postgres-profile-db`,
`rabbitmq-broker`, `game-logic-component`, `api-gateway-component`, `frontend-component`,
`timeout-worker`. El resto debe quedar `Up`.

## 3. Si un servicio falla (`Exited`, `Restarting` o `unhealthy`)

```powershell
docker compose ps -a --format "table {{.Name}}\t{{.Status}}"
docker compose logs --tail=200 <servicio>          # p. ej. game-logic-component
docker inspect --format "{{json .State.Health}}" <contenedor>   # detalle del healthcheck
```

Guarda todos los logs para enviarlos:

```powershell
docker compose logs --no-color --timestamps > compose-logs.txt
```

Antes de compartir `compose-logs.txt`, busca que no contenga contraseñas:
`Select-String compose-logs.txt -Pattern 'password|secret|amqp://|mongodb://' | Select-Object -First 20`.

| Síntoma en el log | Causa probable |
|---|---|
| `required variable ... is missing` | Falta esa variable en `.env` |
| Game Logic: `Timed out while waiting for a server` | MongoDB no listo o `MONGO_*` distinto al del volumen existente |
| Auth: `Schema-validation: missing table` | El volumen de MySQL es anterior al script `Databases/auth/01-init.sql` |
| `ACCESS_REFUSED` (RabbitMQ) | `RABBITMQ_DEFAULT_*` distinto al que creó el volumen `rabbitmq-data` |
| Frontend 503 en `/api/*` | Gateway caído o aún arrancando |
| WebSocket se cierra con 4403 | `WS_ALLOWED_ORIGINS` no coincide con la URL del navegador |

Si un volumen existente tiene otras credenciales, **no lo borres**: vuelve a poner en `.env` las
credenciales originales y avísanos.

## 4. Comprobar cada servicio

```powershell
# Salud (8080, 8081, 8082, 8083 y 8084 están publicados en el equipo)
foreach ($p in 8080,8081,8082,8083,8084) { try { "$p " + (Invoke-RestMethod "http://127.0.0.1:$p/health").status } catch { "$p FALLA: $($_.Exception.Message)" } }

# RabbitMQ: exchanges y colas con consumidores
docker compose exec rabbitmq rabbitmqctl -q list_exchanges name type | Select-String 'user.events|game.events|retry.events'
docker compose exec rabbitmq rabbitmqctl -q list_queues name messages consumers
```

En `list_queues` deben aparecer con `consumers` ≥ 1: `profile.user-registered`,
`profile.game-finished`, `single-player.game-finished` y `multiplayer.game-finished`. Las `.dlq`
deben tener `messages` = 0.

### Auth y Profile/Stats (registro → evento `user.registered` → perfil)

```powershell
$F = 'http://localhost'          # o http://localhost:<FRONTEND_PORT>
$sa = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-RestMethod "$F/api/auth/register" -Method Post -ContentType 'application/json' -Body '{"username":"ana_test","password":"claveSegura123"}'
Invoke-RestMethod "$F/api/auth/login" -Method Post -ContentType 'application/json' -Body '{"username":"ana_test","password":"claveSegura123"}' -WebSession $sa | Select-Object -ExpandProperty user
Start-Sleep 5
Invoke-RestMethod "$F/api/profile/me" -WebSession $sa      # userId, username, createdAt
Invoke-RestMethod "$F/api/stats/me"   -WebSession $sa      # 0, 0, 0, 0
```

Si `/api/profile/me` responde 404 durante más de 10 s, el evento no llegó: revisa
`docker compose logs --tail=100 auth-component profile-stats-component` y la cola
`profile.user-registered` (y su `.dlq`).

Comprobación en las bases (las credenciales se leen dentro del contenedor, no se imprimen):

```powershell
docker compose exec mysql sh -c 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) usuarios FROM users; SELECT COUNT(*) pendientes FROM outbox_events WHERE published_at IS NULL;"'
docker compose exec postgres-profile sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT p.username, s.games_played, s.wins, s.losses, s.draws FROM profiles p JOIN stats s USING (user_id);"'
```

### Game Logic y MongoDB

```powershell
docker compose exec mongo sh -c 'mongosh --quiet -u "$MONGO_APP_USERNAME" -p "$MONGO_APP_PASSWORD" --authenticationDatabase "$MONGO_APP_DATABASE" "$MONGO_APP_DATABASE" --eval "db.games.countDocuments()"'
```

## 5. Partida local y contra Botcito (Single Player)

En el navegador (`http://localhost`), con `ana_test`:

1. Ícono del rey → «Jugar partida guiada» → **Partida local** → Iniciar. Juega `f3`, `e5`, `g4`,
   `Dh4`: debe terminar «Ganan las negras por jaque mate».
2. «Nueva partida» → **Contra Botcito**, nivel 3 → mueve una pieza; el bot debe responder en unos
   segundos («Botcito está pensando…» y luego su jugada).

## 6. Partida completa entre dos usuarios reales (Multiplayer)

Usa dos navegadores distintos, o uno normal y otro en modo incógnito: cada uno tiene su cookie.

1. **Navegador A:** regístrate o entra como `ana_test`. Ícono del rey → «Jugar partida guiada»
   → **Multijugador online** → Blancas, 3 minutos, Privada → Crear partida.
2. Debe verse «Esperando a otro jugador». Pulsa **Copiar enlace**.
3. **Navegador B:** abre el enlace. Te pedirá iniciar sesión: registra `beto_test` (o entra) y
   vuelve sola a la invitación → **Unirme a la partida**.
4. A pasa sola a «Turno: Blancas (tú)». B ve el tablero desde negras.
5. Juega: A `f2-f3`, B `e7-e5`, A `g2-g4`, B `d8-h4`. Cada jugada aparece en el otro navegador.
6. Los relojes: corre solo el del bando con turno y coincide en ambos navegadores.
7. Al cuarto movimiento ambos ven el final: A «Perdiste por jaque mate», B «¡Ganaste! por jaque mate».

Opcional, en otra partida: ofrecer y rechazar tablas, ofrecer y aceptar tablas, rendición con
confirmación y recargar un navegador a mitad de partida (debe recuperar el tablero).

## 7. Estadísticas después de la partida

Solo cuentan las partidas **multijugador** terminadas. Unos segundos después del mate:

```powershell
# 1) Game Logic marcó el evento como entregado al broker
docker compose exec mongo sh -c 'mongosh --quiet -u "$MONGO_APP_USERNAME" -p "$MONGO_APP_PASSWORD" --authenticationDatabase "$MONGO_APP_DATABASE" "$MONGO_APP_DATABASE" --eval "db.games.find({mode:\"multiplayer\",status:\"finished\"},{endReason:1,finishedEventId:1,finishedEventPublished:1}).sort({finishedAt:-1}).limit(3).toArray()"'
# 2) Nada atascado ni en DLQ
docker compose exec rabbitmq rabbitmqctl -q list_queues name messages consumers | Select-String 'game-finished'
# 3) Profile/Stats lo contó
docker compose exec postgres-profile sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT p.username, s.games_played, s.wins, s.losses, s.draws FROM profiles p JOIN stats s USING (user_id);"'
```

Esperado:

1. La partida con `finishedEventPublished: true`.
2. Las colas `*.game-finished` y sus `.dlq` con 0 mensajes.
3. `ana_test` con 1 jugada y 1 derrota, y `beto_test` con 1 jugada y 1 victoria.

En el navegador, `/estadisticas` de cada uno muestra esos números. Con JavaScript desactivado
(DevTools → Ctrl+Shift+P → «Disable JavaScript» → recargar), la página sigue mostrándolos:
eso confirma el renderizado en servidor.

**Si las estadísticas no cambian:**

- `finishedEventPublished: false` durante más de 30 s: Game Logic no llega a RabbitMQ.
  Mira `docker compose logs --tail=100 game-logic-component | Select-String game.finished`.
- Mensajes en `profile.game-finished.dlq`: Profile/Stats rechazó el evento.
  Mira `docker compose logs --tail=100 profile-stats-component`.

## 8. Qué enviarnos

Copia esta tabla con los resultados. Si algo falla, adjunta `compose-logs.txt` (revisado, sección 3)
y la salida de `docker compose ps -a`.

| Paso | Resultado (OK / FALLA + mensaje) |
|---|---|
| 2. `docker compose config --quiet` | |
| 2. Todos `healthy` o `Up` (`ps -a`) | |
| 4. `/health` 8080–8084 | |
| 4. Colas con consumidores, DLQ en 0 | |
| 4. Registro, login y perfil (`/api/profile/me`) | |
| 5. Partida local hasta jaque mate | |
| 5. Partida contra Botcito, el bot responde | |
| 6. Creación, invitación y unión | |
| 6. Jugadas sincronizadas y relojes | |
| 6. Jaque mate visto en ambos navegadores | |
| 7. `finishedEventPublished: true` | |
| 7. Estadísticas 1/1 en `/estadisticas` y en PostgreSQL | |
| 7. `/estadisticas` sin JavaScript | |
