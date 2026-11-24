# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development & Test Commands

### Running Tests

- **Tutor Component (`Backend/tutor-component`)**:
  ```powershell
  cd Backend/tutor-component
  .\venv\Scripts\python -m pytest -q
  ```
  Run a single test file:
  ```powershell
  .\venv\Scripts\python -m pytest tests/test_analyses.py -q
  ```
  Run a single test function:
  ```powershell
  .\venv\Scripts\python -m pytest tests/test_analyses.py::test_create_analysis_success -q
  ```

- **Analysis Worker (`Backend/analysis-worker`)**:
  ```powershell
  cd Backend/analysis-worker
  .\.venv\Scripts\python.exe -m pytest -q
  ```
  Run integration test with real MongoDB:
  ```powershell
  $env:MONGO_TEST_URL = "mongodb://localhost:27018"
  $env:MONGO_TEST_DATABASE = "analysis_worker_test"
  .\.venv\Scripts\python.exe -m pytest -q tests/test_integration_mongo.py
  ```

- **Frontend (`Frontend`)**:
  ```powershell
  cd Frontend
  npm run test
  ```

### Docker Compose Commands

- Validate Compose configuration:
  ```bash
  docker compose config --quiet
  ```
- Build and start all services in detached mode:
  ```bash
  docker compose up --build -d
  ```
- Inspect running containers and logs:
  ```bash
  docker compose ps
  docker compose logs -f <service_name>
  ```
- Stop services:
  ```bash
  docker compose down
  ```

---

## High-Level Architecture & Component Structure

Insightful Games follows a microservice, container-oriented architecture with decoupled logical components communicating over HTTP REST and RabbitMQ event messaging.

### Component Overview

- **Frontend (`Frontend/`)**: React + SSR web presentation component exposing the user interface.
- **WAFs (`waf-web`, `waf-mobile` in `compose.yaml`, image `owasp/modsecurity-crs:nginx`)**: the only services publishing ports (web HTTP→301 and HTTPS :8443; mobile HTTPS :8444). They terminate the public TLS (cert in `EDGE_TLS_DIR`), run ModSecurity + OWASP CRS in blocking mode, and open a new verified TLS connection to their reverse proxy (trusting only the internal CA, `INTERNAL_CA_CERT`). There is no separate WAF compose file and no "direct" mode. See `docs/secure-channel-tls.md`.
- **Reverse proxies (`Backend/reverse-proxy/`, Nginx)**: two containers built from one image with `ENTRY` build arg — `reverse-proxy-web` (`nginx/web.conf.template`, HTTPS :8443 → frontend + web gateway, `/api/ws` WebSocket) and `reverse-proxy-mobile` (`nginx/mobile.conf.template`, HTTPS :8443 → mobile gateway); shared settings and TLS policy in `nginx/common.conf`. No published ports: reached only through their WAF, with internal certificates (`certs/internal`, from `secure-channel/generar_certs_internos.py`) and `Backend/waf/real-ip.conf`. They block `/internal`, drop `X-User-Id` and rate-limit login/register. See `docs/proxy-inverso.md`. Checks: `secure-channel/validar_config.py` (static), `secure-channel/verificar_canal_seguro.py` and `escenarios/medir_resistencia.py` (against the running stack; need `TLS_CA_FILE`).
- **API Gateway (`Backend/api-gateway/`)**: Entry point for all HTTP and WebSocket requests from the web client. Handles JWT validation, injects `X-User-Id`, and **orchestrates** user flows (`Backend/gateway-shared/orchestration/`, shared with the mobile gateway): account-deletion saga, tutor analyses, games vs bot, multiplayer moves/draws. It intercepts mutating WS frames, calls GameLogic/Botcito, then `publish`es to the single-player/multiplayer hubs. It exposes no `/internal` routes.
- **Mobile Gateway (`Backend/api-gateway-mobile/`)**: BFF for the Android app. Calls Auth, Profile/Stats, GameLogic and Tutor directly with its own flows (`GET /home`, `DELETE /auth/account`), and plays **local** games over REST (`POST /games`, `/games/{id}/moves`, `/games/{id}/resign`) with the shared `orchestration` package (publishes to the single-player hub; no Botcito, no vs_bot/multiplayer).
- **Shared orchestration (`Backend/gateway-shared/orchestration/`)**: Python package used by both gateways. Both images build with context `./Backend` (see `Backend/.dockerignore`); locally each gateway's `conftest.py` puts `gateway-shared` on `sys.path`.
- **Network segmentation** (`compose.yaml`): `public_network` (WAFs and proxies) → `private_api` (internal: proxies, frontend, gateways) → `private_back` (internal: gateways, services, workers, brokers, databases). Gateways are the only bridge. Only the WAFs publish host ports; `internal` networks can't publish ports, so to reach an internal service while debugging use `docker compose exec` from a container on its network.
- **Layering rule**: dependencies only go down (client → nginx → gateways → services). No service ever calls a gateway; workers, RabbitMQ consumers and the multiplayer reconnection timer call GameLogic/Botcito directly. See `docs/rediseno-gateways-orquestadores.pdf`.
- **Auth Service (`Backend/auth-component/`)**: Java / Spring Boot service managing user credentials, authentication, JWT tokens, and account deletion. Persists user accounts in MySQL (`mysql-db`).
- **Game Logic (`Backend/GameLogic/`)**: Core chess game state manager. Stores game states, player participation, move histories, FEN positions, and game visibility (`private` vs `shared`) in MongoDB (`mongo-db`).
- **Single Player Service (`Backend/GameService/`)**: WebSocket hub for games vs bot: holds sessions and broadcasts what the gateway publishes; its `game.finished` consumer reads GameLogic directly.
- **Multiplayer (`Backend/multiplayer-component/`, Go)**: WebSocket hub for multiplayer: sessions, presence, reconnection timer (abandons via GameLogic directly) and `publish`.
- **Botcito Component (`Backend/botcito-component/`)**: Chess engine wrapper for position evaluations and move suggestions.
- **Tutor Component (`Backend/tutor-component/`)**: FastAPI service responsible for accepting analysis requests (with a game snapshot supplied by the gateway; it makes no outbound HTTP calls), persisting analysis metadata in MongoDB (`mongo-analysis`), generating deterministic move explanations, handling account anonymization, and publishing `tutor.analysis.requested` events to RabbitMQ.
- **Analysis Worker (`Backend/analysis-worker/`)**: Python 3.12 background process consuming `tutor.analysis.requested` events from RabbitMQ. Evaluates game positions against Botcito-analysis, calculates centipawn losses (`cpLoss`) and move classifications (`best`, `good`, `inaccuracy`, `mistake`, `blunder`), updates analysis results in MongoDB via atomic leases, and handles polling fallback for stale jobs.

### Data Storage & Messaging

- **MongoDB (`mongo-db`)**: Primary game data store for Game Logic.
- **MongoDB Analysis (`mongo-analysis-db`)**: Dedicated database (`insightful_analysis`) for analysis documents created by Tutor and populated asynchronously by Analysis Worker.
- **MySQL (`mysql-db`)**: User authentication and profile persistence.
- **RabbitMQ (`rabbitmq`)**: Event broker hosting topic exchange `tutor.events`, routing key `tutor.analysis.requested`, queue `analysis-worker.requested`, wait/retry exchanges, and dead-letter queue (DLQ).
