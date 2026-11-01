# profile-stats-component

Perfil y contadores de partidas multijugador de cada usuario (contrato v9, sección 8).
Java 21, Spring Boot 4, PostgreSQL y RabbitMQ. Puerto 8087.

No guarda el historial de partidas: eso lo responde Game Logic.

## Rutas internas

Solo se llaman a través del gateway interno. El gateway web y el móvil las publican como
`GET /profile/me` y `GET /stats/me`, poniendo el `userId` del JWT.

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/internal/profile/users/{userId}/profile` | 200 `{ "userId", "username", "createdAt" }` · 404 `PROFILE_NOT_FOUND` |
| GET | `/internal/profile/users/{userId}/stats` | 200 `{ "gamesPlayed", "wins", "losses", "draws" }` |
| DELETE | `/internal/profile/users/{userId}` | 204 siempre, aunque el usuario no exista |
| GET | `/health` | 200 `{ "status": "ok" }` |

Errores con el formato común: `{ "error": { "code", "message" } }`. Un `userId` que no es UUID
responde 400 `VALIDATION_ERROR`.

## Eventos

| Cola | Exchange y clave | Efecto |
|---|---|---|
| `profile.user-registered` | `user.events` / `user.registered` | Crea el perfil y sus contadores en cero |
| `profile.game-finished` | `game.events` / `game.finished` | Suma la partida a cada participante con perfil |

Reglas:

- Solo cuentan partidas `multiplayer` con `result` (`white`, `black` o `draw`). `local`, `vs_bot`
  y `expired` se registran como procesadas sin sumar.
- Victoria si `result` coincide con el color del usuario, derrota si es el otro, tablas si es `draw`.
- Participantes sin perfil y el `userId` anónimo (`00000000-0000-0000-0000-000000000000`) se ignoran;
  no se crean contadores huérfanos.
- Idempotencia: los cambios y el `eventId` se guardan en la misma transacción. Un evento repetido
  no suma dos veces.
- Reintentos (sección 17): si procesar falla, el mensaje va a `retry.events` con `x-retry-count + 1`
  y vuelve a su cola 5 s después. Si `x-retry-count` ya es 5 y vuelve a fallar, va a `<cola>.dlq`.
  Un mensaje que no cumple el contrato va directo a la `.dlq`.
- El mensaje se confirma (ack) después de procesarlo o reenviarlo. Si el reenvío falla porque el
  broker no responde, RabbitMQ lo vuelve a entregar.

## Decisiones propias, pendientes de validar en el contrato

1. **Perfil inexistente → 404 `PROFILE_NOT_FOUND`.** v9 pide crear el perfil al leerlo si no
   existe, pero la ruta interna no trae el `username` y la tabla lo exige. Por ahora el perfil solo
   nace con `user.registered`; `/stats` devuelve ceros sin crear filas. El código de error no está
   en la lista de la sección 20.
2. **Tabla `deleted_users`.** Recuerda las cuentas borradas para que un `user.registered` tardío
   no vuelva a crear el perfil. v9 solo lista `profiles`, `stats` y `processed_events`.
3. **Colas de espera `<cola>.wait`.** v9 define la espera (`x-message-ttl=5000`, dead-letter a la
   cola original) pero no su nombre.
4. **Puerto.** v9 pide `SERVER_PORT` en servicios Java, pero la tabla de Profile/Stats dice `PORT`.
   Se aceptan los dos.

## Configuración

| Variable | Uso | Valor por defecto |
|---|---|---|
| `SERVER_PORT` o `PORT` | Puerto HTTP | `8087` |
| `POSTGRES_URL` | URL JDBC | `jdbc:postgresql://localhost:5432/profile` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | Credenciales de PostgreSQL | `profile` / vacía |
| `RABBITMQ_URL` | `amqp://usuario:clave@host:5672` | `amqp://guest:guest@localhost:5672` |

El esquema lo crea `Databases/profile/01-init.sql`; Hibernate solo lo valida (`ddl-auto: validate`).
Los secretos van en `.env`, nunca en el repositorio.

## Pruebas

No necesitan Docker: usan H2 en modo PostgreSQL con el mismo script de `Databases/profile` y no
conectan con RabbitMQ.

```bash
cd Backend/profile-stats-component
mvn test
```

Requiere JDK 21.

## Integración pendiente

- **Compose:** falta añadir `profile-stats-component`, `postgres-profile` y `rabbitmq` a `compose.yaml`
  (sección 22). Propuesta, sin aplicar:

  ```yaml
  profile-stats-component:
    container_name: profile-stats-component
    build:
      context: ./Backend/profile-stats-component
      dockerfile: Dockerfile
    expose:
      - "8087"
    environment:
      SERVER_PORT: "8087"
      POSTGRES_URL: jdbc:postgresql://postgres-profile:5432/${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      RABBITMQ_URL: amqp://${RABBITMQ_DEFAULT_USER}:${RABBITMQ_DEFAULT_PASS}@rabbitmq:5672
    depends_on:
      postgres-profile:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    networks:
      - app

  postgres-profile:
    image: postgres:17
    container_name: postgres-profile-db
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    expose:
      - "5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./Databases/profile/01-init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      retries: 10
    networks:
      - app
  ```

- **Gateways:** rutas `/profile/me` y `/stats/me` hacia este servicio.
- **Productores:** Auth debe publicar `user.registered` y Game Logic `game.finished`.
- **Sin probar:** PostgreSQL y RabbitMQ reales.
