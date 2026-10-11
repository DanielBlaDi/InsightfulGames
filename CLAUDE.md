# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Insightful Games** — A distributed web platform for learning and playing Chess, Go, and Shogi with an AI-powered pedagogical tutor. Built as a **Prototype 1 vertical slice** demonstrating the full architectural stack.

### Architecture (Distributed, Container-Oriented)

| Service | Language | Framework | Internal Port | Database | Responsibility |
|---------|----------|-----------|---------------|----------|----------------|
| **Frontend** | TypeScript | Vite + React | 80 | — | Web UI, board rendering, WebSocket client |
| **API Gateway** | TypeScript | Fastify | 8080 | — | JWT validation, routing, CORS |
| **Auth** | Java 21 | Spring Boot + Security | 8081 | MySQL | Registration, login, JWT issuance (HS256) |
| **Game Logic** | Java 21 | Spring Boot | 8082 | MongoDB | Chess rules validation, move application, game state |
| **Single Player** | Python 3.12 | FastAPI | 8083 | — | Orchestrates vs_bot games, calls Botcito + Game Logic |
| **Botcito (Stockfish)** | Python 3.12 | FastAPI + python-chess | 8086 | — | Stockfish engine wrapper, best move + evaluation |
| **MySQL** | — | — | 3306 | Relational | Users, auth data |
| **MongoDB** | — | — | 27017 | NoSQL | Game documents (GameState) |

**Connectors**: REST (HTTP/JSON) + WebSocket (real-time moves)  
**Languages**: TypeScript, Java, Python  
**Deployment**: Docker Compose (all services + DBs)

### Key Contracts (from `Documentación/contracts.docx.md`)

- **GameState** — Core domain object with `gameId`, `fen`, `legalMoves`, `moves[]`, `status`, `turn`, `result`, `endReason`
- **Moves** — UCI format (`e2e4`), SAN for display (`e4`)
- **Positions** — FEN strings
- **Auth** — JWT in `Authorization: Bearer <token>` header; WS via `?token=` query
- **Errors** — Uniform shape: `{ "error": { "code": "...", "message": "..." } }`
- **WebSocket** — `/ws/games/{id}?token=<jwt>`; messages: `move`, `resign` → `state`, `move_rejected`, `bot_thinking`, `game_over`

## Development Commands

### Frontend (`InsightfulGames/Frontend`)
```bash
cd InsightfulGames/Frontend
npm run dev       # Start Vite dev server
npm run build     # Type-check (tsc) + production build
npm run lint      # oxlint
npm run preview   # Preview production build
```

### Backend Services (not yet implemented)
Each service will be in `InsightfulGames/Backend/<service-name>/` with its own build/run commands:
- **Auth** (Java/Spring): `./mvnw spring-boot:run`
- **Game Logic** (Java/Spring): `./mvnw spring-boot:run`
- **Single Player** (Python/FastAPI): `uvicorn main:app --reload`
- **Botcito** (Python/FastAPI): `uvicorn main:app --reload`
- **Gateway** (TypeScript/Fastify): `npm run dev`

### Docker Compose (to be created)
```bash
docker compose up -d       # Start all services + DBs
docker compose logs -f     # Follow logs
docker compose down        # Stop and remove
```

## File Structure (Current State)

```
InsightfulGames/
├── Frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Landing.tsx    # Main landing page (converted from HTML)
│   │   │   └── Login.tsx      # Auth form
│   │   ├── App.tsx            # Routes between Landing and Login
│   │   └── main.tsx           # React entry point
│   ├── index.html             # Includes Tailwind CDN + custom config + Google Fonts
│   ├── package.json
│   └── vite.config.ts
├── Backend/                   # Empty — services to be implemented
├── Databases/                 # Empty — SQL/init scripts to be added
├── Documentación/             # Requirements, contracts, stack definition
│   ├── Requisitos project.md
│   ├── Stack tecnológico.md
│   ├── contracts.docx.md
│   └── [SwArch_2026ii] - Project - Prototype 1.pdf
└── CLAUDE.md                  # This file
```

## Prototype 1 Scope (Vertical Slice)

**In scope**:
- User registration + login (JWT)
- Chess only (not Go/Shogi yet)
- **Local 1v1** (same device, hot-seat)
- **vs Bot** (Stockfish via Botcito, skill level 1–20)
- Game state persisted in MongoDB
- WebSocket real-time updates
- Board modal with Chess/Go/Shogi previews (UI only)

**Out of scope** (later prototypes):
- Multiplayer online (matchmaking, Elo, WebSocket rooms)
- Tutor LLM integration (post-game analysis)
- Go/Shogi game logic engines
- Replay system
- Competitive ranked mode

## Implementation Notes

### Frontend
- Tailwind via CDN in `index.html` (custom theme with design tokens)
- Google Fonts: Playfair Display (headlines), Plus Jakarta Sans (body), Material Symbols Outlined
- Landing page is a single large component; consider splitting into sections (Hero, Features, Games, Modal) when expanding
- `Landing.tsx` handles modal state (`isModalOpen`, `activeBoard`, `boardRotated`)

### Contracts First
All service communication must follow `Documentación/contracts.docx.md`. When implementing a new service:
1. Define its OpenAPI/REST endpoints per the contract
2. Use exact `GameState` shape and error codes
3. Validate JWT at Gateway level (`HS256`, secret `JWT_SECRET`)

### Data Flow (vs_bot example)
```
Frontend (WS move) 
  → Gateway (JWT check, X-User-Id) 
  → Single Player (turn check) 
  → Game Logic (validate + apply move, persist) 
  → Single Player (if bot's turn) 
    → Gateway → Botcito (fen + level) 
  → Single Player (apply bot move) 
  → Game Logic (validate + apply, persist) 
  → Frontend (state + game_over)
```

### Environment Variables (from contracts)
| Variable | Used By | Example |
|----------|---------|---------|
| `JWT_SECRET` | Gateway, Auth | shared secret |
| `AUTH_URL` | Gateway | `http://auth:8081` |
| `SINGLE_PLAYER_URL` | Gateway | `http://single-player:8083` |
| `BOTCITO_URL` | Gateway | `http://botcito:8086` |
| `GATEWAY_INTERNAL_URL` | Single Player | `http://gateway:8080` |
| `GAME_LOGIC_URL` | Single Player | `http://game-logic:8082` |
| `MYSQL_URL` | Auth | `jdbc:mysql://mysql:3306/auth` |
| `MONGO_URL` | Game Logic | `mongodb://mongo:27017/games` |
| `STOCKFISH_PATH` | Botcito | `/usr/games/stockfish` |

## Next Steps Priority

1. **Docker Compose** — Scaffold all services + DBs with healthchecks
2. **Botcito** — Stockfish wrapper (simplest, enables vs_bot)
3. **Game Logic** — Chess rules, MongoDB persistence
4. **Auth** — Spring Security + MySQL + JWT
5. **Gateway** — Fastify routing + JWT validation
6. **Single Player** — Orchestration + WebSocket server
7. **Frontend integration** — Connect real WS, replace mock board modal