"""Partida local en vivo desde la app: POST /games, /games/{id}/moves y /games/{id}/resign.
Game Logic y el hub de Single Player se simulan con httpx.MockTransport (ver test_gateway.Internal)."""

import json

import httpx
import pytest

from test_gateway import GAME, OTHER, USER, auth, env  # noqa: F401  (env es la fixture)

LOGIC_GAMES = "/internal/logic/games"
PUBLISH = f"/internal/single-player/games/{GAME}/publish"


def local_state(version=0, status="in_progress", participants=None, **extra):
    return {
        "gameId": GAME, "mode": "local", "visibility": "private", "status": status, "turn": "white",
        "version": version, "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "legalMoves": {"e2": ["e3", "e4"]}, "moves": [], "result": None, "endReason": None,
        "participants": participants if participants is not None else [
            {"userId": USER, "color": "white"}, {"userId": USER, "color": "black"},
        ],
        **extra,
    }


def sent_json(internal, method, path):
    request = next(c for c in internal.calls if c.method == method and c.url.path == path)
    return json.loads(request.content)


# ------------------------------------------------------------------ crear


def test_create_local_game_for_both_colors(env):
    client, internal = env
    internal.on("POST", LOGIC_GAMES, 201, local_state())
    r = client.post("/games", json={"mode": "local", "timeControl": {"minutes": 10}}, headers=auth())
    assert r.status_code == 201, r.text
    assert r.json()["gameId"] == GAME
    body = sent_json(internal, "POST", LOGIC_GAMES)
    assert body["mode"] == "local" and body["botLevel"] is None
    assert body["participants"] == [{"userId": USER, "color": "white"}, {"userId": USER, "color": "black"}]
    assert body["timeControl"] == {"minutes": 10} and body["visibility"] == "private"


def test_create_game_rate_limit_returns_429_before_game_logic(env):
    client, internal = env
    internal.on("POST", LOGIC_GAMES, 201, local_state())

    for _ in range(5):
        r = client.post(
            "/games",
            json={"mode": "local", "timeControl": {"minutes": 10}},
            headers=auth(),
        )
        assert r.status_code == 201

    blocked = client.post(
        "/games",
        json={"mode": "local", "timeControl": {"minutes": 10}},
        headers=auth(),
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert len([call for call in internal.calls if call.url.path == LOGIC_GAMES]) == 5


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "vs_bot", "botLevel": 3, "playerColor": "white"},
        {"mode": "multiplayer"},
        {},
    ],
)
def test_app_only_creates_local_games(env, payload):
    client, internal = env
    r = client.post("/games", json=payload, headers=auth())
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert internal.calls == []


@pytest.mark.parametrize(
    "content",
    [b"", b"no es json", b"[1, 2]", json.dumps({"mode": "local", "timeControl": {"minutes": 5}}).encode()],
)
def test_create_validation(env, content):
    client, internal = env
    r = client.post("/games", content=content, headers={**auth(), "Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert internal.calls == []


# ------------------------------------------------------------------ jugar


def test_move_returns_new_state_and_publishes(env):
    client, internal = env
    internal.on("GET", f"{LOGIC_GAMES}/{GAME}", 200, local_state(version=3))
    internal.on("POST", f"{LOGIC_GAMES}/{GAME}/moves", 200, local_state(version=4, turn="black"))
    internal.on("POST", PUBLISH, 204)
    r = client.post(f"/games/{GAME}/moves", json={"uci": "e2e4", "expectedVersion": 3}, headers=auth())
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 4
    assert sent_json(internal, "POST", f"{LOGIC_GAMES}/{GAME}/moves") == {"uci": "e2e4", "expectedVersion": 3}
    assert sent_json(internal, "POST", PUBLISH)["state"]["version"] == 4


def test_move_works_when_hub_is_down(env):
    client, internal = env
    internal.on("GET", f"{LOGIC_GAMES}/{GAME}", 200, local_state(version=0))
    internal.on("POST", f"{LOGIC_GAMES}/{GAME}/moves", 200, local_state(version=1))
    internal.on("POST", PUBLISH, exc=httpx.ConnectError("hub caído"))
    r = client.post(f"/games/{GAME}/moves", json={"uci": "e2e4", "expectedVersion": 0}, headers=auth())
    assert r.status_code == 200
    assert r.json()["version"] == 1


@pytest.mark.parametrize(
    "status,code",
    [(409, "VERSION_CONFLICT"), (422, "ILLEGAL_MOVE"), (422, "GAME_FINISHED")],
)
def test_move_errors_from_game_logic_pass_through(env, status, code):
    client, internal = env
    internal.on("GET", f"{LOGIC_GAMES}/{GAME}", 200, local_state(version=5))
    internal.on("POST", f"{LOGIC_GAMES}/{GAME}/moves", status, {"error": {"code": code, "message": "no"}})
    internal.on("POST", PUBLISH, 204)
    r = client.post(f"/games/{GAME}/moves", json={"uci": "e2e5", "expectedVersion": 1}, headers=auth())
    assert r.status_code == status
    assert r.json()["error"]["code"] == code


def test_move_on_finished_game_is_rejected_without_calling_move(env):
    client, internal = env
    internal.on("GET", f"{LOGIC_GAMES}/{GAME}", 200, local_state(status="finished"))
    r = client.post(f"/games/{GAME}/moves", json={"uci": "e2e4", "expectedVersion": 0}, headers=auth())
    assert r.status_code == 422 and r.json()["error"]["code"] == "GAME_FINISHED"
    assert not any(c.url.path.endswith("/moves") for c in internal.calls)


def test_move_on_someone_elses_game_is_404(env):
    client, internal = env
    others = [{"userId": OTHER, "color": "white"}, {"userId": OTHER, "color": "black"}]
    internal.on("GET", f"{LOGIC_GAMES}/{GAME}", 200, local_state(participants=others, visibility="shared"))
    r = client.post(f"/games/{GAME}/moves", json={"uci": "e2e4", "expectedVersion": 0}, headers=auth())
    assert r.status_code == 404 and r.json()["error"]["code"] == "GAME_NOT_FOUND"


@pytest.mark.parametrize(
    "payload",
    [{"expectedVersion": 0}, {"uci": "e2e4"}, {"uci": "e2e4", "expectedVersion": "0"}, {"uci": "", "expectedVersion": 0}],
)
def test_move_validation(env, payload):
    client, internal = env
    r = client.post(f"/games/{GAME}/moves", json=payload, headers=auth())
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert internal.calls == []


# ------------------------------------------------------------------ rendirse


def test_resign_local_game_with_side(env):
    client, internal = env
    internal.on("GET", f"{LOGIC_GAMES}/{GAME}", 200, local_state())
    internal.on("POST", f"{LOGIC_GAMES}/{GAME}/resign", 200,
                local_state(status="finished", result="white", endReason="surrender"))
    internal.on("POST", PUBLISH, 204)
    r = client.post(f"/games/{GAME}/resign", json={"side": "black"}, headers=auth())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "finished"
    assert sent_json(internal, "POST", f"{LOGIC_GAMES}/{GAME}/resign") == {"side": "black"}


def test_resign_local_game_needs_side(env):
    client, internal = env
    internal.on("GET", f"{LOGIC_GAMES}/{GAME}", 200, local_state())
    r = client.post(f"/games/{GAME}/resign", json={}, headers=auth())
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


# ------------------------------------------------------------------ comunes


@pytest.mark.parametrize("path", ["/games", f"/games/{GAME}/moves", f"/games/{GAME}/resign"])
def test_live_routes_need_bearer(env, path):
    client, internal = env
    r = client.post(path, json={"mode": "local"})
    assert r.status_code == 401
    assert internal.calls == []


@pytest.mark.parametrize("path", ["/games/no-es-uuid/moves", "/games/no-es-uuid/resign"])
def test_live_routes_reject_malformed_ids(env, path):
    client, internal = env
    r = client.post(path, json={"uci": "e2e4", "expectedVersion": 0, "side": "white"}, headers=auth())
    assert r.status_code == 404 and r.json()["error"]["code"] == "GAME_NOT_FOUND"
    assert internal.calls == []


def test_unreachable_game_logic_is_503(env):
    client, internal = env
    internal.on("POST", LOGIC_GAMES, exc=httpx.ConnectError("caído"))
    r = client.post("/games", json={"mode": "local"}, headers=auth())
    assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICES_UNAVAILABLE"
