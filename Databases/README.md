# Inicialización de bases de datos

Las imágenes oficiales ejecutan `/docker-entrypoint-initdb.d` **solo la primera vez, con el volumen vacío**. Si el volumen ya tiene datos, estos scripts se ignoran.

| Base | Servicio Compose | Script | Qué crea | Qué crea la aplicación |
|---|---|---|---|---|
| MySQL de Auth | `mysql` | `auth/01-init.sql` | Tabla `users` | Auth crea `outbox_events` al arrancar (`db/outbox.sql`) |
| PostgreSQL de Profile/Stats | `postgres-profile` | `profile/01-init.sql` | `profiles`, `stats`, `processed_events`, `deleted_users` | Nada: Hibernate solo valida |
| MongoDB de partidas | `mongo` | `mongo/init-mongo.sh` | Usuario de aplicación con `readWrite` | Game Logic debe crear sus índices al arrancar (GL-07, pendiente) |
| MongoDB de análisis | `mongo-analysis` | `mongo/init-mongo.sh` | Usuario de aplicación con `readWrite` | Tutor crea `analyses` y sus índices al arrancar |

La base y el usuario de MySQL y PostgreSQL los crea cada imagen a partir de las variables del entorno, con permisos suficientes sobre su base. Por eso no hay scripts de usuarios ni de permisos.

`mongo/init-mongo.sh` se reutiliza en las dos instancias de MongoDB. Compose le pasa `MONGO_APP_DATABASE`, `MONGO_APP_USERNAME` y `MONGO_APP_PASSWORD` distintos en cada una, y por eso los usuarios quedan separados.

RabbitMQ no es una base de datos: no tiene scripts aquí. Cada servicio declara su topología al conectarse.

Reglas:
- No agregar datos de ejemplo, ni índices que el contrato asigne a la aplicación.
- Los scripts de esta carpeta no borran datos.
- Un cambio de esquema sobre un volumen con datos no se resuelve recreando el volumen. Ver `DOCKER_DEPLOYMENT.md`.
