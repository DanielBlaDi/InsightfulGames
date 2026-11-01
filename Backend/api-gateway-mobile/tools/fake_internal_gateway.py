"""Gateway interno SIMULADO, solo para desarrollo de la app y del gateway móvil.

Mientras el gateway web real no publique /internal/* y no existan Profile/Stats y
Multiplayer, este servidor responde lo mismo que dirían según los contratos v9.

Uso (puerto 8080 = el que usa GATEWAY_INTERNAL_URL):
    JWT_SECRET=<el mismo del gateway móvil> uvicorn fake_internal_gateway:app --port 8080

Variables opcionales:
    MOCK_FAIL=stats,recentGames   -> esas secciones de /home responden 503 (para ver 'No disponible')
    MOCK_GAMES=45                 -> cantidad de partidas de cada usuario (por defecto 45)
"""

import base64
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import FastAPI, Header, Query
from fastapi.responses import JSONResponse

JWT_SECRET = os.environ["JWT_SECRET"]
FAIL = {s.strip() for s in os.getenv("MOCK_FAIL", "").split(",") if s.strip()}
N_GAMES = int(os.getenv("MOCK_GAMES", "45"))

app = FastAPI(title="Gateway interno simulado")
USERS: dict[str, dict] = {}


def err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _id(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


# --------------------------------------------------------------------- auth


@app.post("/internal/auth/register", status_code=201)
def register(body: dict):
    username = body.get("username", "")
    if not 3 <= len(username) <= 20 or len(body.get("password", "")) < 8:
        return err(400, "VALIDATION_ERROR", "Campos inválidos")
    if username in USERS:
        return err(409, "USERNAME_TAKEN", "El nombre de usuario ya existe")
    USERS[username] = {
        "userId": str(uuid.uuid4()),
        "password": body["password"],
        "createdAt": iso(datetime.now(timezone.utc)),
    }
    return {"userId": USERS[username]["userId"], "username": username}


@app.post("/internal/auth/login")
def login(body: dict):
    user = USERS.get(body.get("username", ""))
    if not user or user["password"] != body.get("password"):
        return err(401, "INVALID_CREDENTIALS", "Usuario o contraseña incorrectos")
    token = jwt.encode(
        {"sub": user["userId"], "username": body["username"], "exp": int(time.time()) + 3600},
        JWT_SECRET,
        algorithm="HS256",
    )
    return {
        "accessToken": token,
        "expiresIn": 3600,
        "user": {"userId": user["userId"], "username": body["username"]},
    }


# ------------------------------------------------------------ datos simulados


def user_by_id(user_id: str):
    for name, u in USERS.items():
        if u["userId"] == user_id:
            return name, u
    return None, None


def games_for(user_id: str) -> list[dict]:
    """Más reciente primero. Mezcla los tres modos y varios finales."""
    base = datetime.now(timezone.utc) - timedelta(minutes=5)
    modes = ["multiplayer", "vs_bot", "local", "multiplayer", "vs_bot"]
    finals = [
        ("white", "checkmate"), ("black", "timeout"), ("draw", "stalemate"),
        ("black", "surrender"), ("white", "abandonment"),
    ]
    out = []
    for i in range(N_GAMES):
        mode = modes[i % len(modes)]
        result, reason = finals[i % len(finals)]
        status = "finished"
        if i == 0 and mode == "multiplayer":
            status, result, reason = "in_progress", None, None
        if i == 3:
            mode, status, result, reason = "multiplayer", "finished", None, "expired"
        if i == 1:
            mode, status, result, reason = "multiplayer", "waiting", None, None
        game_id = _id(f"{user_id}-game-{i}")
        out.append({
            "gameId": game_id,
            "mode": mode,
            "matchId": _id(f"{user_id}-match-{i}") if mode == "multiplayer" else None,
            "status": status,
            "result": result,
            "endReason": reason,
            "color": None if mode == "local" else ("white" if i % 2 == 0 else "black"),
            "createdAt": iso(base - timedelta(hours=3 * i)),
        })
    return out


def game_state(summary: dict, user_id: str) -> dict:
    mode = summary["mode"]
    me = {"userId": user_id, "color": summary["color"] or "white"}
    other = "black" if me["color"] == "white" else "white"
    participants = [me]
    if mode == "local":
        participants = [{"userId": user_id, "color": "white"}, {"userId": user_id, "color": "black"}]
    elif mode == "multiplayer" and summary["status"] != "waiting" and summary["endReason"] != "expired":
        participants.append({"userId": _id("rival"), "color": other})
    sans = [("e4", "e2e4"), ("e5", "e7e5"), ("Nf3", "g1f3"), ("Nc6", "b8c6")]
    return {
        "gameId": summary["gameId"],
        "mode": mode,
        "visibility": "private",
        "matchId": summary["matchId"],
        "participants": participants,
        "botLevel": 8 if mode == "vs_bot" else None,
        "timeControl": {"minutes": 10} if mode == "multiplayer" else None,
        "clocks": None,
        "status": summary["status"],
        "turn": "white",
        "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
        "initialFen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "legalMoves": {},
        "moves": [
            {"ply": i + 1, "color": "white" if i % 2 == 0 else "black", "san": s, "uci": u,
             "fenAfter": "...", "timestamp": summary["createdAt"]}
            for i, (s, u) in enumerate(sans)
        ],
        "drawOffer": None,
        "version": len(sans),
        "result": summary["result"],
        "endReason": summary["endReason"],
        "createdAt": summary["createdAt"],
        "finishedAt": None if summary["status"] != "finished" else summary["createdAt"],
    }


# ------------------------------------------------------------ perfil y stats


@app.get("/internal/profile/users/{user_id}/profile")
def profile(user_id: str):
    if "profile" in FAIL:
        return err(503, "SERVICES_UNAVAILABLE", "simulado")
    name, u = user_by_id(user_id)
    if not u:
        return err(404, "NOT_FOUND", "Perfil inexistente")
    return {"userId": user_id, "username": name, "createdAt": u["createdAt"]}


@app.get("/internal/profile/users/{user_id}/stats")
def stats(user_id: str):
    if "stats" in FAIL:
        return err(503, "SERVICES_UNAVAILABLE", "simulado")
    played = [g for g in games_for(user_id) if g["mode"] == "multiplayer" and g["result"]]
    wins = sum(1 for g in played if g["result"] == g["color"])
    draws = sum(1 for g in played if g["result"] == "draw")
    return {"gamesPlayed": len(played), "wins": wins, "losses": len(played) - wins - draws, "draws": draws}


# ------------------------------------------------------------------- partidas


@app.get("/internal/logic/games")
def list_games(userId: str, limit: int = Query(20, ge=1, le=20), cursor: str | None = None):
    if "recentGames" in FAIL:
        return err(503, "SERVICES_UNAVAILABLE", "simulado")
    offset = int(base64.urlsafe_b64decode(cursor.encode()).decode()) if cursor else 0
    games = games_for(userId)
    page = games[offset: offset + limit]
    nxt = offset + limit
    next_cursor = base64.urlsafe_b64encode(str(nxt).encode()).decode() if nxt < len(games) else None
    return {"items": page, "nextCursor": next_cursor}


def _find(user_id: str, key: str, value: str):
    return next((g for g in games_for(user_id) if g[key] == value), None)


@app.get("/internal/single-player/games/{game_id}")
def single_player_game(game_id: str, x_user_id: str | None = Header(default=None)):
    if not x_user_id:
        return err(401, "UNAUTHORIZED", "Falta X-User-Id: el gateway debe ponerlo")
    g = _find(x_user_id, "gameId", game_id)
    if not g or g["mode"] == "multiplayer":
        return err(404, "GAME_NOT_FOUND", "La partida no existe o no es visible")
    return game_state(g, x_user_id)


@app.get("/internal/multiplayer/matches/{match_id}")
def multiplayer_match(match_id: str, x_user_id: str | None = Header(default=None)):
    if not x_user_id:
        return err(401, "UNAUTHORIZED", "Falta X-User-Id: el gateway debe ponerlo")
    g = _find(x_user_id, "matchId", match_id)
    if not g:
        return err(404, "MATCH_NOT_FOUND", "La partida no existe o no es visible")
    return game_state(g, x_user_id)
