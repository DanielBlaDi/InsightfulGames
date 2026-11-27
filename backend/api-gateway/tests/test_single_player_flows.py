"""Flows de Single Player en el gateway web: Game Logic, Botcito y el hub (publish) simulados."""

import asyncio
import json
import os
import time

os.environ.update(JWT_SECRET="x" * 40, WS_ALLOWED_ORIGINS="http://localhost")

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from main import app
from orchestration import single_player
from orchestration.context import Ctx, GameLocks

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
GID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def token(user):
    return jwt.encode({"sub": user, "exp": int(time.time()) + 60}, "x" * 40, algorithm="HS256")


class World:
    """Game Logic con estado (version, expectedVersion), Botcito y el hub de Single Player."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.games: dict[str, dict] = {}
        self.engine_error: tuple[int, str] | None = None  # (estado, código)
        self.engine_move = "e7e5"
        self.logic_error: tuple[int, dict] | None = None  # respuesta fija a POST /games
        self.hub_down = False
        self.next_id = GID
        self.delay = 0.0
        self.active = {}
        self.max_active = {}
        self.total_active = 0
        self.peak = 0

    # ---- helpers de las pruebas
    def add(self, **fields) -> dict:
        game = {
            "gameId": GID, "mode": "local", "visibility": "private", "matchId": None,
            "participants": [{"userId": A, "color": "white"}, {"userId": A, "color": "black"}],
            "botLevel": None, "timeControl": None, "clocks": None, "status": "in_progress", "turn": "white",
            "fen": "fen-0", "initialFen": "fen-0", "legalMoves": {}, "moves": [], "drawOffer": None,
            "version": 0, "result": None, "endReason": None, "createdAt": "t", "finishedAt": None,
        }
        game.update(fields)
        self.games[game["gameId"]] = game
        return game

    def calls_to(self, suffix):
        return [c for c in self.calls if c.url.path.endswith(suffix)]

    def body(self, request):
        return json.loads(request.content) if request.content else None

    def published(self):
        return [self.body(c) for c in self.calls_to("/publish")]

    def logic_calls(self):
        return [c for c in self.calls if c.url.path.startswith("/internal/logic/")]

    # ---- servicios simulados
    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path, method = request.url.path, request.method
        body = self.body(request)

        if path.startswith("/internal/single-player/"):
            if self.hub_down:
                raise httpx.ConnectError("hub caído")
            return httpx.Response(204)

        if path == "/internal/engine/best-move":
            if self.engine_error:
                status, code = self.engine_error
                return httpx.Response(status, json={"error": {"code": code, "message": f"Botcito: {code}"}})
            return httpx.Response(200, json={"uci": self.engine_move, "san": "x", "evaluation": None})

        gid = path.rsplit("/", 2)[-2] if path.endswith(("/moves", "/resign", "/visibility")) else path.rsplit("/", 1)[-1]
        self.active[gid] = self.active.get(gid, 0) + 1
        self.max_active[gid] = max(self.max_active.get(gid, 0), self.active[gid])
        self.total_active += 1
        self.peak = max(self.peak, self.total_active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return self.logic(method, path, body)
        finally:
            self.active[gid] -= 1
            self.total_active -= 1

    def logic(self, method, path, body) -> httpx.Response:
        if path == "/internal/logic/games" and method == "POST":
            if self.logic_error:
                status, payload = self.logic_error
                return httpx.Response(status, json=payload)
            game = self.add(**{k: body[k] for k in ("mode", "visibility", "participants", "botLevel", "timeControl")},
                            gameId=self.next_id)
            if body["mode"] == "vs_bot":
                game["fen"] = "fen-0"
            return httpx.Response(201, json=game)
        parts = path.split("/")  # ['', 'internal', 'logic', 'games', id, action?]
        game = self.games.get(parts[4])
        if game is None:
            return httpx.Response(404, json={"error": {"code": "GAME_NOT_FOUND", "message": "no existe"}})
        action = parts[5] if len(parts) > 5 else ""
        if (method, action) == ("GET", ""):
            return httpx.Response(200, json=game)
        if method in ("POST", "PATCH") and action in ("moves", "visibility"):
            if body["expectedVersion"] != game["version"]:
                return httpx.Response(409, json={"error": {"code": "VERSION_CONFLICT", "message": "versión distinta"}})
            game["version"] += 1
            if action == "moves":
                color = game["turn"]
                game["moves"] = game["moves"] + [{"ply": len(game["moves"]) + 1, "color": color, "uci": body["uci"]}]
                game["turn"] = "black" if color == "white" else "white"
            else:
                game["visibility"] = body["visibility"]
            return httpx.Response(200, json=game)
        if (method, action) == ("POST", "resign"):
            game.update(status="finished", result="black" if body["side"] == "white" else "white",
                        endReason="surrender", version=game["version"] + 1)
            return httpx.Response(200, json=game)
        return httpx.Response(404, json={})


@pytest.fixture
def env():
    world = World()
    with TestClient(app) as client:
        app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(world.handler))
        client.headers["Authorization"] = f"Bearer {token(A)}"
        yield client, world


def as_user(client, user):
    client.headers["Authorization"] = f"Bearer {token(user)}"


def error_code(r):
    return r.json()["error"]["code"]


# ============================================================ crear


@pytest.mark.parametrize("body", [
    {"mode": "multiplayer"}, {}, {"mode": "vs_bot", "playerColor": "white"},
    {"mode": "vs_bot", "botLevel": 0, "playerColor": "white"}, {"mode": "vs_bot", "botLevel": 21, "playerColor": "white"},
    {"mode": "vs_bot", "botLevel": "5", "playerColor": "white"}, {"mode": "vs_bot", "botLevel": True, "playerColor": "white"},
    {"mode": "vs_bot", "botLevel": 5, "playerColor": "green"}, {"mode": "vs_bot", "level": 5, "playerColor": "white"},
    {"mode": "local", "timeControl": {"minutes": 5}}, {"mode": "local", "timeControl": {}},
    {"mode": "local", "timeControl": 10}, {"mode": "local", "visibility": "public"}, {"mode": "local", "visibility": 5},
])
def test_invalid_creation_requests_are_validation_errors_and_call_nobody(env, body):
    client, world = env
    r = client.post("/games", json=body)
    assert r.status_code == 400 and error_code(r) == "VALIDATION_ERROR"
    assert world.calls == []


@pytest.mark.parametrize("content", [b"", b"no es json", b"[1]", b"5"])
def test_missing_or_malformed_body_is_a_validation_error(env, content):
    client, world = env
    r = client.post("/games", content=content, headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and error_code(r) == "VALIDATION_ERROR"
    assert world.calls == []


def test_local_game_sends_two_participants_with_the_same_user_and_defaults_to_private(env):
    client, world = env
    # botLevel y playerColor se ignoran en local
    r = client.post("/games", json={"mode": "local", "botLevel": 7, "playerColor": "black"})
    assert r.status_code == 201 and r.json()["gameId"] == GID and r.json()["version"] == 0
    sent = world.body(world.calls_to("/internal/logic/games")[0])
    assert sent == {
        "mode": "local", "timeControl": None, "visibility": "private", "botLevel": None,
        "participants": [{"userId": A, "color": "white"}, {"userId": A, "color": "black"}],
    }
    assert world.calls_to("/best-move") == []
    assert all("x-user-id" not in c.headers for c in world.calls)  # servicio a servicio: sin X-User-Id


def test_bot_game_sends_only_the_human_and_forwards_time_control_and_visibility(env):
    client, world = env
    r = client.post("/games", json={"mode": "vs_bot", "botLevel": 5, "playerColor": "white",
                                    "timeControl": {"minutes": 10}, "visibility": "shared"})
    assert r.status_code == 201
    sent = world.body(world.calls_to("/internal/logic/games")[0])
    assert sent["participants"] == [{"userId": A, "color": "white"}]
    assert sent["botLevel"] == 5 and sent["timeControl"] == {"minutes": 10} and sent["visibility"] == "shared"
    assert world.calls_to("/best-move") == []


def test_bot_game_as_black_lets_the_bot_open_with_the_current_version(env):
    client, world = env
    r = client.post("/games", json={"mode": "vs_bot", "botLevel": 7, "playerColor": "black"})
    assert r.status_code == 201
    assert r.json()["version"] == 1 and r.json()["moves"][0]["uci"] == "e7e5"
    assert world.body(world.calls_to("/best-move")[0]) == {"fen": "fen-0", "botLevel": 7}
    assert world.body(world.calls_to("/moves")[0]) == {"uci": "e7e5", "expectedVersion": 0}
    # orden: crear -> bot_thinking al hub -> Botcito -> mover -> state al hub
    order = [c.url.path.split("/")[2] + ":" + c.url.path.rsplit("/", 1)[-1] for c in world.calls]
    assert order == ["logic:games", "single-player:publish", "engine:best-move", "logic:moves", "single-player:publish"]
    first, second = world.published()
    assert first == {"signal": {"type": "bot_thinking"}}
    assert second["lastMove"] == "e7e5" and second["state"]["version"] == 1 and "gameOver" not in second


def test_bot_failure_on_creation_still_returns_the_game_and_warns_the_clients(env):
    client, world = env
    world.engine_error = (503, "ENGINE_BUSY")
    r = client.post("/games", json={"mode": "vs_bot", "botLevel": 5, "playerColor": "black"})
    assert r.status_code == 201 and r.json()["version"] == 0  # la partida se devuelve igual
    assert world.calls_to("/moves") == []
    assert world.published()[-1] == {"signal": {"type": "error", "code": "ENGINE_BUSY", "message": "Botcito: ENGINE_BUSY"}}


def test_bot_timeout_keeps_its_real_code_in_the_signal(env):
    client, world = env
    world.engine_error = (504, "ENGINE_TIMEOUT")
    client.post("/games", json={"mode": "vs_bot", "botLevel": 5, "playerColor": "black"})
    assert world.published()[-1]["signal"]["code"] == "ENGINE_TIMEOUT"


def test_game_logic_errors_on_creation_pass_through_with_their_code(env):
    client, world = env
    world.logic_error = (400, {"error": {"code": "VALIDATION_ERROR", "message": "participants inválidos"}})
    r = client.post("/games", json={"mode": "local"})
    assert r.status_code == 400 and error_code(r) == "VALIDATION_ERROR" and "participants" in r.json()["error"]["message"]


@pytest.mark.parametrize("reply", [(500, {"x": 1}), (502, {}), (503, {"error": {"code": "OTRO", "message": "m"}})])
def test_game_logic_5xx_on_creation_is_services_unavailable(env, reply):
    client, world = env
    world.logic_error = reply
    r = client.post("/games", json={"mode": "local"})
    assert r.status_code == 503 and error_code(r) == "SERVICES_UNAVAILABLE"
    assert world.published() == []


def test_a_hub_that_is_down_never_fails_the_request(env):
    client, world = env
    world.hub_down = True
    r = client.post("/games", json={"mode": "vs_bot", "botLevel": 5, "playerColor": "black"})
    assert r.status_code == 201 and r.json()["version"] == 1


def test_create_requires_a_session(env):
    client, world = env
    del client.headers["Authorization"]
    assert client.post("/games", json={"mode": "local"}).status_code == 401
    assert world.calls == []


# ============================================================ leer


def test_participant_reads_the_game(env):
    client, world = env
    world.add()
    r = client.get(f"/games/{GID}")
    assert r.status_code == 200 and r.json()["gameId"] == GID
    assert [c.url.path for c in world.calls] == [f"/internal/logic/games/{GID}"]


def test_non_participants_and_multiplayer_games_are_not_found(env):
    client, world = env
    world.add()
    as_user(client, B)
    r = client.get(f"/games/{GID}")
    assert r.status_code == 404 and error_code(r) == "GAME_NOT_FOUND"
    as_user(client, A)
    world.add(mode="multiplayer", participants=[{"userId": A, "color": "white"}])
    r = client.get(f"/games/{GID}")
    assert r.status_code == 404 and error_code(r) == "GAME_NOT_FOUND"


def test_shared_games_can_be_read_by_anyone(env):
    client, world = env
    world.add(visibility="shared")
    as_user(client, B)
    assert client.get(f"/games/{GID}").status_code == 200


def test_unknown_game_is_game_not_found_with_logics_code(env):
    client, world = env
    r = client.get(f"/games/{GID}")
    assert r.status_code == 404 and error_code(r) == "GAME_NOT_FOUND"


@pytest.mark.parametrize("failure", [httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_game_logic_unreachable_is_503(env, failure):
    client, world = env

    async def boom(request):
        raise failure

    app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    r = client.get(f"/games/{GID}")
    assert r.status_code == 503 and error_code(r) == "SERVICES_UNAVAILABLE"


def test_malformed_game_id_never_reaches_a_service(env):
    client, world = env
    r = client.get("/games/no-es-uuid")
    assert r.status_code == 404 and error_code(r) == "GAME_NOT_FOUND"
    assert world.calls == []


# ============================================================ rendirse


def test_resign_in_bot_game_uses_the_humans_color_and_ignores_the_given_side(env):
    client, world = env
    world.add(mode="vs_bot", participants=[{"userId": A, "color": "black"}], botLevel=5, turn="black")
    r = client.post(f"/games/{GID}/resign", json={"side": "white"})
    assert r.status_code == 200 and r.json()["status"] == "finished" and r.json()["result"] == "white"
    assert world.body(world.calls_to("/resign")[0]) == {"side": "black"}
    published = world.published()[-1]
    assert published["state"]["status"] == "finished" and "lastMove" not in published


def test_resign_in_local_game_needs_a_valid_side(env):
    client, world = env
    world.add()
    for body in (None, {}, {"side": "green"}):
        r = client.post(f"/games/{GID}/resign", json=body) if body is not None else client.post(f"/games/{GID}/resign")
        assert r.status_code == 400 and error_code(r) == "VALIDATION_ERROR"
    assert world.calls_to("/resign") == []
    r = client.post(f"/games/{GID}/resign", json={"side": "white"})
    assert r.status_code == 200 and world.body(world.calls_to("/resign")[0]) == {"side": "white"}


def test_only_participants_can_resign(env):
    client, world = env
    world.add()
    as_user(client, B)
    r = client.post(f"/games/{GID}/resign", json={"side": "white"})
    assert r.status_code == 404 and error_code(r) == "GAME_NOT_FOUND"
    assert world.calls_to("/resign") == []


def test_resigning_a_finished_game_passes_logics_error_through(env):
    client, world = env
    world.add()

    def finished(method, path, body):
        return httpx.Response(409, json={"error": {"code": "GAME_NOT_IN_PROGRESS", "message": "ya terminó"}})

    original = world.logic
    world.logic = lambda m, p, b: finished(m, p, b) if p.endswith("/resign") else original(m, p, b)
    r = client.post(f"/games/{GID}/resign", json={"side": "white"})
    assert r.status_code == 409 and error_code(r) == "GAME_NOT_IN_PROGRESS"
    assert world.published() == []


def test_the_lock_of_a_finished_game_is_released(env):
    client, world = env
    world.add()
    client.post(f"/games/{GID}/resign", json={"side": "white"})
    assert GID not in app.state.locks._locks


# ============================================================ visibilidad


def test_visibility_is_forwarded_with_the_expected_version_and_published_without_game_over(env):
    client, world = env
    world.add(version=4)
    r = client.patch(f"/games/{GID}/visibility", json={"visibility": "shared", "expectedVersion": 4})
    assert r.status_code == 200 and r.json()["visibility"] == "shared" and r.json()["version"] == 5
    assert world.body(world.calls_to("/visibility")[0]) == {"visibility": "shared", "expectedVersion": 4}
    published = world.published()[-1]
    assert published["state"]["version"] == 5 and published["gameOver"] is False


@pytest.mark.parametrize("body", [{"visibility": "public", "expectedVersion": 1}, {"visibility": "shared"},
                                  {"visibility": "shared", "expectedVersion": "1"}, {"expectedVersion": 1}, {}])
def test_visibility_validates_before_calling_anyone(env, body):
    client, world = env
    r = client.patch(f"/games/{GID}/visibility", json=body)
    assert r.status_code == 400 and error_code(r) == "VALIDATION_ERROR"
    assert world.calls == []


def test_only_participants_may_change_the_visibility(env):
    client, world = env
    world.add(version=1)
    as_user(client, B)
    r = client.patch(f"/games/{GID}/visibility", json={"visibility": "shared", "expectedVersion": 1})
    assert r.status_code == 404 and error_code(r) == "GAME_NOT_FOUND"
    assert world.calls_to("/visibility") == []


def test_visibility_version_conflict_is_propagated(env):
    client, world = env
    world.add(version=4)
    r = client.patch(f"/games/{GID}/visibility", json={"visibility": "shared", "expectedVersion": 3})
    assert r.status_code == 409 and error_code(r) == "VERSION_CONFLICT"
    assert world.published() == []


# ============================================================ concurrencia


def run_flow(world, coroutines):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(world.handler)) as client:
            ctx = Ctx(client=client, upstreams={
                "logic": "http://logic", "engine": "http://engine", "single-player": "http://sp",
            }, locks=GameLocks(), timeout=5)
            return await asyncio.gather(*(c(ctx) for c in coroutines))
    return asyncio.run(go())


def test_operations_on_the_same_game_are_serialized_and_different_games_are_not():
    world = World()
    world.delay = 0.05
    g2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    world.add(version=0)
    world.add(gameId=g2, version=0)

    def vis(game_id, expected):
        body = json.dumps({"visibility": "shared", "expectedVersion": expected}).encode()
        return lambda ctx: single_player.change_visibility(ctx, A, game_id, body)

    # Dos cambios sobre la MISMA partida: con el lock, el segundo ve la version ya subida (no hay carrera)
    results = run_flow(world, [vis(GID, 0), vis(GID, 1)])
    assert [r["version"] for r in results] == [1, 2]
    assert world.max_active[GID] == 1

    # Partidas distintas sí avanzan en paralelo (las llamadas a Game Logic se solapan)
    world.peak = 0
    run_flow(world, [vis(GID, 2), vis(g2, 0)])
    assert world.peak == 2
    assert world.games[g2]["version"] == 1 and world.games[GID]["version"] == 3
