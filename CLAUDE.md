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
- **API Gateway (`Backend/api-gateway/`)**: Entry point for all HTTP requests from clients. Handles JWT validation, injects internal headers (`X-User-Id`), and routes requests to downstream services.
- **Auth Service (`Backend/auth-component/`)**: Java / Spring Boot service managing user credentials, authentication, JWT tokens, and account deletion. Persists user accounts in MySQL (`mysql-db`).
- **Game Logic (`Backend/GameLogic/`)**: Core chess game state manager. Stores game states, player participation, move histories, FEN positions, and game visibility (`private` vs `shared`) in MongoDB (`mongo-db`).
- **Single Player Service (`Backend/GameService/`)**: Manages single-player sessions and interacts with Botcito engine services.
- **Botcito Component (`Backend/botcito-component/`)**: Chess engine wrapper for position evaluations and move suggestions.
- **Tutor Component (`Backend/tutor-component/`)**: FastAPI service responsible for accepting analysis requests, validating game states against Game Logic, persisting analysis metadata in MongoDB (`mongo-analysis`), generating deterministic move explanations, handling account anonymization, and publishing `tutor.analysis.requested` events to RabbitMQ.
- **Analysis Worker (`Backend/analysis-worker/`)**: Python 3.12 background process consuming `tutor.analysis.requested` events from RabbitMQ. Evaluates game positions against Botcito-analysis, calculates centipawn losses (`cpLoss`) and move classifications (`best`, `good`, `inaccuracy`, `mistake`, `blunder`), updates analysis results in MongoDB via atomic leases, and handles polling fallback for stale jobs.

### Data Storage & Messaging

- **MongoDB (`mongo-db`)**: Primary game data store for Game Logic.
- **MongoDB Analysis (`mongo-analysis-db`)**: Dedicated database (`insightful_analysis`) for analysis documents created by Tutor and populated asynchronously by Analysis Worker.
- **MySQL (`mysql-db`)**: User authentication and profile persistence.
- **RabbitMQ (`rabbitmq`)**: Event broker hosting topic exchange `tutor.events`, routing key `tutor.analysis.requested`, queue `analysis-worker.requested`, wait/retry exchanges, and dead-letter queue (DLQ).
