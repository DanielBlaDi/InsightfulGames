# Despliegue Docker de Insightful Games

Referencia normativa: `CONTRATO_TECNICO_DEFINITIVO.md`, sección 16. Hoja de ruta: `PLAN_DE_IMPLEMENTACION_Y_VALIDACION.md`.

## 1. Estado real

**Este paquete nunca se ha levantado.** En el entorno donde se preparó no hay acceso al socket de Docker, así que no se construyó ninguna imagen ni se arrancó ningún contenedor. Se validó la configuración, no el funcionamiento.

**Aunque arranque, el sistema aún no está completo.** Compose prepara la infraestructura, pero faltan funciones en el código:

| Área | Estado del código | Efecto en el despliegue |
|---|---|---|
| Frontend | Sin Vike ni `Frontend/Dockerfile` | No hay interfaz web. Servicio `frontend` en perfil `pendiente` |
| Multiplayer, Timeout Worker, Analysis Worker | No existen | Perfil `pendiente` |
| Botcito-análisis | Sin rutas propias | Perfil `pendiente` |
| Gateway web | Sin `/internal/*` ni cookie | El gateway móvil recibe 404 de sus llamadas internas y Auth no puede completar un borrado |
| Single Player | Llama a rutas que Game Logic ya no expone | Arranca, pero no crea partidas |
| Game Logic | Sin publicación final ni índices | Arranca, pero no publica al terminar partidas |

Hito alcanzable con este paquete: **H0** del plan, que es Compose arriba y registro con creación de perfil por RabbitMQ.

## 2. Arquitectura desplegada

| Grupo | Servicios | Publicado en el host |
|---|---|---|
| Por defecto | `api-gateway-mobile` | `${MOBILE_GATEWAY_PORT}`, 8090 |
| Por defecto | `api-gateway-component`, `auth-component`, `game-logic-component`, `single-player-component`, `tutor-component`, `botcito-component`, `profile-stats-component` | No |
| Por defecto | `mysql`, `mongo`, `mongo-analysis`, `postgres-profile`, `rabbitmq` | No |
| Perfil `pendiente` | `frontend` | `${FRONTEND_PORT}`, 80 |
| Perfil `pendiente` | `multiplayer-component`, `botcito-analysis-component`, `timeout-worker`, `analysis-worker` | No |

Red: `app`. Volúmenes: `mysql-data`, `mongo-data`, `mongo-analysis-data`, `postgres-data`, `rabbitmq-data`.

Android no es un contenedor: se conecta a `api-gateway-mobile`.

## 3. Requisitos

- Docker Engine con Compose v2.20 o superior, porque se usa `required: false` en `depends_on`.
- Permiso sobre Docker. Si `docker ps` responde `permission denied`:

```bash
sudo usermod -aG docker "$USER"
```

Después cerrar sesión y volver a entrar. Pertenecer al grupo `docker` equivale a tener privilegios de administrador en esa máquina.

## 4. Instalación

### 4.1 Revisar volúmenes existentes

Antes del primer arranque, comprobar si ya hay datos:

```bash
docker volume ls --filter label=com.docker.compose.project=insightfulgames
```

Si aparece alguno, leer la sección 8 antes de continuar.

### 4.2 Crear `.env`

Si no existe `.env`:

```bash
cp .env.example .env
chmod 600 .env
while grep -q '=CHANGE_ME$' .env; do
  sed -i "0,/=CHANGE_ME$/s//=$(openssl rand -hex 24)/" .env
done
```

Comprobar:

```bash
grep -c '=CHANGE_ME$' .env    # debe ser 0
git check-ignore .env         # debe imprimir .env
```

`JWT_SECRET` queda con 48 caracteres, más que los 32 bytes exigidos. Usar solo letras y números en las contraseñas, porque forman parte de URLs de conexión. No cambiar contraseñas después del primer arranque sin leer la sección 8.3.

### 4.3 Validar la configuración

```bash
docker compose config --quiet
docker compose --profile pendiente config --quiet
```

### 4.4 Construir y arrancar

```bash
docker compose build
docker compose up -d --wait
docker compose ps
```

El primer `build` descarga dependencias de Maven, Gradle y pip y puede tardar bastante. `--wait` termina cuando todo está `healthy`, o falla si algún servicio no lo logra.

No usar `--profile pendiente` hasta que existan esos servicios: `build` fallará porque faltan sus carpetas y Dockerfiles.

## 5. Inicialización de bases de datos

| Base | Qué hace el script | Qué hace la aplicación |
|---|---|---|
| MySQL | `Databases/auth/01-init.sql` crea `users` | Auth crea `outbox_events` al arrancar |
| PostgreSQL | `Databases/profile/01-init.sql` crea sus cuatro tablas | Hibernate solo valida |
| MongoDB partidas | `Databases/mongo/init-mongo.sh` crea el usuario | Game Logic debe crear índices (GL-07, pendiente) |
| MongoDB análisis | El mismo script, con otras variables | Tutor crea colección e índices |

**Limitación.** Las imágenes oficiales solo ejecutan estos scripts con el volumen vacío. Con un volumen existente no corren, y cambiar un script no tiene efecto.

Los montajes usan `create_host_path: false`: si falta un script, Compose falla en lugar de crear un directorio y dejar una base sin esquema.

## 6. Validación

Comprobaciones del hito H0.

**Salud:**

```bash
docker compose ps --format '{{.Service}} {{.Health}}'
```

**Puertos publicados.** Solo debe aparecer `api-gateway-mobile`:

```bash
docker compose ps --format '{{.Service}} {{.Publishers}}'
```

**Bases:**

```bash
docker compose exec mysql sh -c 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SHOW TABLES"'
docker compose exec postgres-profile sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
```

MySQL debe mostrar `users` y `outbox_events`, y PostgreSQL sus cuatro tablas.

**RabbitMQ:**

```bash
docker compose exec rabbitmq rabbitmqctl list_exchanges name type durable
docker compose exec rabbitmq rabbitmqctl list_queues name durable messages
```

Deben aparecer `user.events`, `game.events`, `retry.events`, `tutor.events` y las colas `profile.*` con sus `.wait` y `.dlq`.

**Registro real.** Se usa el contenedor del gateway móvil porque el gateway web no está publicado:

```bash
docker compose exec api-gateway-mobile python -c "
import json, urllib.request
r = urllib.request.Request('http://api-gateway-component:8080/auth/register',
    data=json.dumps({'username': 'prueba_h0', 'password': 'prueba-h0-1234'}).encode(),
    headers={'Content-Type': 'application/json'})
print(urllib.request.urlopen(r, timeout=10).status)"

docker compose exec postgres-profile sh -c \
  "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"SELECT username FROM profiles\""
```

Debe imprimir `201` y mostrar `prueba_h0`. Este usuario queda guardado.

**Variables obligatorias.** Con un `.env` sin `JWT_SECRET` o sin `WS_ALLOWED_ORIGINS`, `docker compose config` debe fallar.

Las validaciones completas por hito están en las secciones 8 y 12 del plan.

## 7. Operación

```bash
docker compose logs -f auth-component     # registros de un servicio
docker compose restart auth-component     # reiniciar uno
docker compose up -d --build auth-component   # reconstruir tras cambiar su código
docker compose stop                       # detener, conserva todo
docker compose down                       # quitar contenedores y red, conserva volúmenes
```

**No usar `docker compose down -v`, `docker volume prune` ni `docker system prune --volumes`.** Eliminan datos.

### Respaldos

Crear `backups/`, que está en `.gitignore`. Los respaldos contienen datos reales.

```bash
mkdir -p backups
docker compose exec -T mysql sh -c 'mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' > backups/mysql.sql
docker compose exec -T postgres-profile sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backups/postgres.sql
docker compose exec -T mongo sh -c 'mongodump --quiet --archive -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin' > backups/mongo.archive
docker compose exec -T mongo-analysis sh -c 'mongodump --quiet --archive -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin' > backups/mongo-analysis.archive
```

Comprobar que los archivos no estén vacíos, y probar la restauración en un proyecto aislado antes de confiar en ellos.

### Pruebas sin tocar los datos de trabajo

Un proyecto con otro nombre usa volúmenes propios:

```bash
docker compose -p insightful-audit up -d --wait
docker compose -p insightful-audit ps
```

Solo sobre ese proyecto, tras confirmar con `ps` que es el correcto, se puede limpiar con `docker compose -p insightful-audit down -v`.

### Acceso de depuración local

La configuración normal no publica nada interno. Si hace falta, crear `compose.dev.yaml`, sin versionarlo, y activarlo de forma explícita:

```yaml
services:
  rabbitmq:
    ports:
      - "127.0.0.1:15672:15672"
  api-gateway-component:
    ports:
      - "127.0.0.1:8080:8080"
```

```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d
```

Ligar siempre a `127.0.0.1`: las rutas internas no validan identidad.

## 8. Volúmenes existentes y cambios de esquema

### 8.1 Un volumen ya inicializado

Los scripts no vuelven a correr. Si Auth falla con una tabla ausente, el script es idempotente y se puede aplicar a mano:

```bash
docker compose exec -T mysql sh -c 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < Databases/auth/01-init.sql
docker compose exec -T postgres-profile sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < Databases/profile/01-init.sql
```

Para MongoDB, `init-mongo.sh` comprueba si el usuario existe antes de crearlo, y se puede ejecutar dentro del contenedor con sus variables.

### 8.2 Datos del prototipo

DP-03 permite retirarlos, pero no de forma indiscriminada. Seguir la sección 16.8 del contrato: identificar, respaldar, obtener confirmación escrita con la lista exacta y retirar uno por uno.

```bash
docker volume inspect insightfulgames_mysql-data
docker volume rm insightfulgames_mysql-data     # solo tras esos pasos
```

### 8.3 Cambiar una contraseña

Cambiarla en `.env` no la cambia dentro de una base ya inicializada: la aplicación dejará de conectar. Primero hay que cambiarla en el motor, y luego en `.env`.

## 9. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `permission denied ... docker.sock` | Usuario fuera del grupo `docker` | Sección 3 |
| `required variable ... is missing` | Falta una variable en `.env` | Compararlo con `.env.example` |
| `build` falla en `Backend/multiplayer-component` | Perfil `pendiente` activo | No usar ese perfil todavía |
| Error de bind al arrancar una base | Falta un script en `Databases/` | Restaurar el archivo. No crear un directorio |
| Auth reinicia con `JWT_SECRET debe tener al menos 32 bytes` | Secreto corto | Generarlo de nuevo |
| Auth reinicia con `Schema-validation: missing table` | Volumen ya inicializado sin esquema | Sección 8.1 |
| `Access denied` o `Authentication failed` en una base | Contraseña de `.env` distinta a la del volumen | Sección 8.3 |
| Tutor en `unhealthy` | Mongo de análisis no acepta credenciales, o `init-mongo.sh` no corrió | Revisar `docker compose logs mongo-analysis` y la sección 8.1 |
| `api-gateway-component` no arranca | Espera a todos sus servicios | `docker compose ps` indica cuál falla |
| Healthcheck Java falla con `bash: not found` | La imagen no trae `bash` | Hay que cambiar la comprobación. Se validará en el primer arranque |
| Gateway móvil responde 404 en `/auth/login` | Falta el passthrough (GW-04) | Es esperado hoy |
| Perfil no aparece tras registrar | Cola sin consumidor o broker caído | Revisar logs de Auth y Profile/Stats. El evento queda en `outbox_events` |
| Puerto 8090 ocupado | Otro proceso lo usa | Cambiar `MOBILE_GATEWAY_PORT` |

## 10. Producción

No hay dominio definido. Antes de desplegar:
- Fijar `WS_ALLOWED_ORIGINS` con el dominio real y `https`.
- Usar `COOKIE_SECURE=true`.
- Generar secretos nuevos, sin reutilizar los locales.
- Limitar quién accede al grupo `docker`.
