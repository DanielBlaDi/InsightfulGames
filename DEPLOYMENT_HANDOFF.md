# Entrega del paquete de despliegue

Preparado el 2 de noviembre de 2026 en la copia `InsightfulGames` del entorno aislado, sobre el commit `a2605cc`, rama `containers`. **No se hicieron commits.** Guía de uso: `DOCKER_DEPLOYMENT.md`.

**Resumen:** la configuración está validada, pero **nada se ha construido ni ejecutado**, porque este entorno no tiene acceso a Docker. Cinco servicios del alcance no se pueden construir hoy porque su código no existe.

## 1. Archivos creados

| Archivo | Propósito |
|---|---|
| `.env` | Entorno local con secretos aleatorios. Permisos 600. **No se traslada** |
| `DOCKER_DEPLOYMENT.md` | Guía de instalación, operación y problemas |
| `DEPLOYMENT_HANDOFF.md` | Este documento |
| `Databases/README.md` | Qué inicializa cada script y qué hace la aplicación |

## 2. Archivos modificados

| Archivo | Cambio | Motivo |
|---|---|---|
| `compose.yaml` | Reescrito según la sección 16 del contrato | Faltaban 5 servicios de infraestructura y datos, rutas mal escritas, puertos internos publicados y variables que el código no lee |
| `.env.example` | Reescrito | Tenía `BOTSITO_PORT`, Redis y puertos internos, y le faltaban PostgreSQL, RabbitMQ y Mongo de análisis |
| `.gitignore` | Agrega `backups/` | Los respaldos contienen datos. `.env` ya estaba ignorado y `.env.example` ya estaba permitido |

Cambios de `compose.yaml` que conviene revisar:
- Se quitó la publicación de 8080, 8081, 8082, 8083 y 8086.
- Se quitaron `INTERNAL_COMPAT`, `USE_MOCK`, `CORS_ORIGINS`, `BOTCITO_COMPONENT_URL`, `GATEWAY_URL` y `extra_hosts`.
- En Single Player se quitó `GAME_LOGIC_URL`.
- Se corrigió `fronted-component` a `frontend-component`.
- `name` pasa a minúscula, sin efecto: Compose ya lo normalizaba a `insightfulgames`, comprobado con la versión anterior, y los volúmenes conservan su nombre.

## 3. Archivos conservados sin cambios

- Todo el código de `Backend/`, `Frontend/` y `mobile/`, incluidos sus Dockerfiles.
- `Databases/auth/01-init.sql`, `Databases/profile/01-init.sql`, `Databases/mongo/init-mongo.sh`, `Databases/.gitkeep`.
- `Frontend/.env.example`.
- `Backend/docker-compose.dev.yml`, `Backend/api-gateway/docker-compose.yml` y `Backend/botcito-component/compose.yaml`. El plan retira los dos primeros en INF-15. No se tocaron para limitar este paquete.

## 4. Scripts de `/Databases`

| Script | Estado | Uso |
|---|---|---|
| `auth/01-init.sql` | Reutilizado | MySQL |
| `profile/01-init.sql` | Reutilizado. Ya existía, pero no estaba montado | PostgreSQL |
| `mongo/init-mongo.sh` | Reutilizado en las dos instancias de MongoDB | Usuario de aplicación |

**No hizo falta ningún script nuevo.** Los esquemas coinciden con las entidades de Auth y Profile/Stats por lectura de código. Usuarios y permisos de MySQL y PostgreSQL los crean las imágenes. `outbox_events` lo crea Auth. Los índices de Game Logic y Tutor pertenecen a la aplicación según el contrato. RabbitMQ no tiene archivo de definiciones porque cada servicio declara su topología.

## 5. Variables por revisar al trasladar

| Variable | Revisar |
|---|---|
| `WS_ALLOWED_ORIGINS` | Debe coincidir con el origen real del navegador |
| `COOKIE_SECURE` | `true` con HTTPS |
| `FRONTEND_PORT`, `MOBILE_GATEWAY_PORT` | Conflictos en la máquina destino. `FRONTEND_PORT` cambia `WS_ALLOWED_ORIGINS` |
| `ENGINE_VERSION` | Confirmar `Stockfish 15.1` dentro de la imagen |
| `ENGINE_POOL_SIZE`, `ENGINE_TIMEOUT_MS`, `ANALYSIS_STALE_MINUTES`, `TIMEOUT_BATCH_LIMIT`, `ANALYSIS_MAX_REACTIVATIONS` | Valores propuestos, por medir (DP-17) |

**Variables que Compose ya pasa, pero el código aún no lee.** El contrato las exige y se activan con estas tareas:

| Servicio | Variables | Tarea |
|---|---|---|
| Gateway web | `WS_ALLOWED_ORIGINS`, `COOKIE_SECURE`, `GAME_LOGIC_URL`, `TUTOR_URL`, `PROFILE_URL`, `MULTIPLAYER_URL`, `BOTCITO_ANALYSIS_URL`, `PORT` | GW-03, GW-02, GW-04, GW-05, GW-10 |
| Gateway móvil | `PORT` | GWM-01 |
| Game Logic | `RABBITMQ_URL`, `WAITING_TIMEOUT_MINUTES` | GL-05, GL-11 |
| Single Player | `RABBITMQ_URL` | SP-09 |
| Botcito | `PORT`, `ENGINE_ROLE`, `ENGINE_POOL_SIZE`, `ENGINE_THREADS`, `ENGINE_TIMEOUT_MS` | BOT-04, BOT-06, BA-01 |
| Tutor | `ANALYSIS_MAX_REACTIVATIONS` | TUT-07 |

Hasta entonces, cada servicio usa su valor por defecto. Por ejemplo, Game Logic intentaría RabbitMQ en `localhost`, y el gateway web no valida `Origin`.

## 6. Secretos que deben generarse de nuevo para producción

`JWT_SECRET`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `MONGO_PASSWORD`, `MONGO_ROOT_PASSWORD`, `MONGO_ANALYSIS_PASSWORD`, `POSTGRES_PASSWORD` y `RABBITMQ_DEFAULT_PASS`.

Los de este `.env` son solo locales. Cambiar `JWT_SECRET` invalida las sesiones activas. Cambiar una contraseña con un volumen ya inicializado exige cambiarla también en el motor.

## 7. Archivos que deben copiarse al repositorio real

Copiar:
- `compose.yaml`
- `.env.example`
- `.gitignore`
- `Databases/README.md`
- `DOCKER_DEPLOYMENT.md`
- `DEPLOYMENT_HANDOFF.md`, opcional

**No copiar `.env`.** El repositorio real genera el suyo con la sección 4.2 de `DOCKER_DEPLOYMENT.md`.

## 8. Pasos después de copiarlos

1. Comprobar que el repositorio real contiene `Databases/` y las carpetas de `Backend/` con esa capitalización.
2. Revisar los volúmenes existentes y respaldarlos (INF-01). Si hay datos del prototipo, seguir la sección 16.8 del contrato.
3. Generar `.env`.
4. Ejecutar `docker compose config --quiet`.
5. Ejecutar `docker compose build`.
6. Ejecutar `docker compose up -d --wait`.
7. Seguir las validaciones de la sección 6 de `DOCKER_DEPLOYMENT.md`.
8. Registrar los resultados en este documento o en el plan.

## 9. Validaciones que pasaron

Solo validan la configuración.

| Validación | Resultado |
|---|---|
| `docker compose config --quiet` con `.env` | Pasa |
| Lo mismo con `--profile pendiente` | Pasa: 18 servicios |
| Lo mismo con `.env.example` | Pasa |
| Falta de `JWT_SECRET` o `WS_ALLOWED_ORIGINS` | Compose falla, como debe |
| Variables de `compose.yaml`, `.env` y `.env.example` | Conjuntos idénticos, sin variables sin resolver |
| Valores `CHANGE_ME` en `.env` | Ninguno |
| Secretos dentro de `compose.yaml` | Ninguno |
| `.env` ignorado y sin versionar; `.env.example` versionable | Correcto |
| Puertos publicados | Solo 80 (perfil `pendiente`) y 8090 |
| Hosts de todas las URLs internas | Coinciden con servicios de Compose |
| Scripts montados | Existen, solo lectura, `create_host_path: false` |
| Servicios sin healthcheck | Ninguno |
| Volúmenes | 5 volúmenes nombrados |
| `bash -n` sobre `init-mongo.sh` | Pasa |
| Búsqueda de operaciones destructivas en `Databases/` y `compose.yaml` | Sin resultados |

## 10. Validaciones pendientes

| Validación | Motivo |
|---|---|
| `docker compose build` | Sin acceso a Docker |
| `docker compose up` y healthchecks | Sin acceso a Docker |
| Ejecución de scripts SQL y de MongoDB | Sin motores ni Docker |
| Healthcheck Java con `bash` y `/dev/tcp` | Requiere la imagen |
| Persistencia de volúmenes | Sin acceso a Docker |
| Topología real de RabbitMQ | Sin broker |
| Registro con perfil de extremo a extremo (H0) | Sin acceso a Docker |
| Stockfish dentro de la imagen | Sin acceso a Docker |
| Cualquier flujo web, WebSocket o Android | El código aún no los implementa |

## 11. Decisiones y problemas antes del despliegue

| Problema | Por qué importa | Propuesta |
|---|---|---|
| **Sin frontend Vike** | No existen servidor Node ni `Frontend/Dockerfile`, así que no hay web. No se sustituyó por Nginx | Implementar FE-12, FE-14 y FE-20. Mientras tanto, `frontend` queda en perfil `pendiente` |
| **Tres servicios Go sin código** | Sus carpetas no existen | Implementar MP-00, TW-00 y AW-00, y asignar responsables |
| **Ruta del binario Go** | El contrato solo dice "opción `-health`". Compose asume `/app/<nombre>` | Decidirlo en esas tareas y ajustar Compose si difiere |
| **Dockerfiles en minúscula** | El contrato pide `Dockerfile`, pero `Backend/api-gateway/dockerfile` existe en minúscula. No se renombró para no tocar componentes | Aplicar INF-03 y cambiar esa línea de Compose |
| **Single Player sin `GAME_LOGIC_URL`** | El contrato la retira, pero el código la lee. Sin ella apunta a `localhost`. Hoy tampoco funciona, porque usa rutas inexistentes | Se resuelve con SP-01 |
| **Índices de Game Logic** | No existen hasta GL-07. Sin ellos no hay unicidad de `matchId` | Implementar GL-07. No se duplicó en un script porque el contrato lo asigna a la aplicación |
| **Dominio de producción** | No existe en el repositorio | Definirlo antes de desplegar (INF-22) |
| **Acceso a Docker** | Bloquea toda validación real | Dar acceso y ejecutar la sección 8 |

## 12. Inventario de la inspección

- **Componentes con código y Dockerfile:** gateway web, gateway móvil, Auth, Game Logic, Single Player, Tutor, Botcito-juego, Profile/Stats.
- **Sin código o sin imagen válida:** Frontend Vike, Multiplayer, Timeout Worker, Analysis Worker, Botcito-análisis.
- **Bases:** MySQL de Auth, MongoDB de Game Logic, PostgreSQL de Profile/Stats, MongoDB de análisis. RabbitMQ es mensajería.
- **Scripts faltantes:** ninguno.
- **Dockerfiles faltantes:** `Frontend/Dockerfile`, y los de `Backend/multiplayer-component`, `Backend/timeout-worker` y `Backend/analysis-worker`.
- **Documentación histórica:** `contracts.docx` no está en este entorno. No se usó.
