"""Flows REST de Multiplayer en el gateway web: Game Logic y el hub (publish) simulados."""

import asyncio
import hashlib
import json
import os
import time

os.environ.update(JWT_SECRET="x" * 40, WS_ALLOWED_ORIGINS="http://localhost")

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from main import app
from orchestration import multiplayer
from orchestration.context import Ctx, GameLocks

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
C = "33333333-3333-4333-8333-333333333333"
MATCH = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
GAME = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def token(user):
    return jwt.encode({"sub": user, "exp": int(time.time()) + 60}, "x" * 40, algorithm="HS256")


class World:
    """Game Logic con estado para partidas multiplayer (idempotencia de creación, join, resign, visibilidad)
    y el hub de Multiplayer."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.games: dict[str, dict] = {}
        self.by_creation: dict[str, str] = {}
        self.hub_down = False
        self.logic_error: tuple[int, dict | None] | None = None  # respuesta fija a todo lo de Game Logic
        self.delay = 0.0
        self.active = 0
        self.peak = 0

    def add(self, **fields) -> dict:
        game = {
            "gameId": GAME, "matchId": MATCH, "mode": "multiplayer", "visibility": "private",
            "participants": [{"userId": A, "color": "white"}], "status": "waiting", "turn": "white",
            "version": 0, "moves": [], "result": None, "endReason": None, "drawOffer": None,
            "createdAt": "2026-11-02T10:00:00Z", "finishedAt": None,
        }
        game.update(fields)
        self.games[game["gameId"]] = game
        return game

    def body(self, request):
        return json.loads(request.content) if request.content else None

    def calls_to(self, suffix):
        return [c for c in self.calls if c.url.path.endswith(suffix)]

    def published(self):
        return [self.body(c) for c in self.calls_to("/publish")]

    def logic_calls(self):
        return [c for c in self.calls if c.url.path.startswith("/internal/logic/")]

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path, method = request.url.path, request.method
        if path.startswith("/internal/multiplayer/"):
            if self.hub_down:
                raise httpx.ConnectError("hub caído")
            return httpx.Response(204)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.logic_error:
                status, payload = self.logic_error
                return httpx.Response(status, json=payload) if payload is not None else httpx.Response(status, text="x")
            return self.logic(method, path, self.body(request))
        finally:
            self.active -= 1

    def logic(self, method, path, body) -> httpx.Response:
        if path == "/internal/logic/games" and method == "POST":
            key = body["creationKey"]
            if key in self.by_creation:
                game = self.games[self.by_creation[key]]
                if game["fingerprint"] != body["requestFingerprint"]:
                    return httpx.Response(409, json={"error": {"code": "IDEMPOTENCY_KEY_REUSED", "message": "key reused"}})
                return httpx.Response(200, json=game)
            game = self.add(gameId=f"cccccccc-cccc-4ccc-8ccc-{len(self.games):012d}", matchId=body["matchId"],
                            visibility=body["visibility"], participants=body["participants"],
                            timeControl=body["timeControl"])
            game["fingerprint"] = body["requestFingerprint"]
            self.by_creation[key] = game["gameId"]
            return httpx.Response(201, json=game)
        parts = path.split("/")  # ['', 'internal', 'logic', 'games', ...]
        if parts[4] == "by-match":
            game = next((g for g in self.games.values() if g["matchId"] == parts[5]), None)
            if game is None:
                return httpx.Response(404, json={"error": {"code": "GAME_NOT_FOUND", "message": "missing"}})
            return httpx.Response(200, json=game)
        game = self.games.get(parts[4])
        if game is None:
            return httpx.Response(404, json={"error": {"code": "GAME_NOT_FOUND", "message": "missing"}})
        action = parts[5] if len(parts) > 5 else ""
        if (method, action) == ("POST", "join"):
            if game["status"] != "waiting":
                return httpx.Response(409, json={"error": {"code": "GAME_NOT_WAITING", "message": "not waiting"}})
            game["participants"] = game["participants"] + [{"userId": body["userId"], "color": "black"}]
            game.update(status="in_progress", version=game["version"] + 1)
            return httpx.Response(200, json=game)
        if (method, action) == ("POST", "resign"):
            if game["status"] == "finished":
                return httpx.Response(422, json={"error": {"code": "GAME_FINISHED", "message": "already finished"}})
            game.update(status="finished", result="0-1" if body["side"] == "white" else "1-0",
                        endReason="resignation", version=game["version"] + 1)
            return httpx.Response(200, json=game)
        if (method, action) == ("POST", "moves"):
            if body["expectedVersion"] != game["version"]:
                return httpx.Response(409, json={"error": {"code": "VERSION_CONFLICT", "message": "stale"}})
            if body["uci"] == "e2e5":
                return httpx.Response(422, json={"error": {"code": "INVALID_MOVE", "message": "Jugada ilegal"}})
            color = game["turn"]
            game.update(moves=game["moves"] + [{"uci": body["uci"], "color": color}],
                        turn="black" if color == "white" else "white", version=game["version"] + 1)
            return httpx.Response(200, json=game)
        if (method, action) == ("POST", "draw"):
            operation = parts[6]
            if operation == "offer":
                game.update(drawOffer=body["side"])
            elif operation == "accept":
                game.update(status="finished", result="1/2-1/2", endReason="draw_agreement", drawOffer=None)
            else:
                game.update(drawOffer=None)
            game["version"] += 1
            return httpx.Response(200, json=game)
        if (method, action) == ("PATCH", "visibility"):
            if body["expectedVersion"] != game["version"]:
                return httpx.Response(409, json={"error": {"code": "VERSION_CONFLICT", "message": "stale"}})
            game.update(visibility=body["visibility"], version=game["version"] + 1)
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


def code(r):
    return r.json()["error"]["code"]


def create(client, body=None, key="k-1"):
    return client.post("/matches", json={"creatorColor": "white"} if body is None else body,
                       headers={"Idempotency-Key": key} if key is not None else {})


# ================================================================== crear


def test_create_defaults_and_payload_for_game_logic(env):
    client, world = env
    r = create(client)
    assert r.status_code == 201 and "idempotency-replayed" not in r.headers
    body = r.json()
    assert set(body) == {"matchId", "status", "createdAt"} and body["status"] == "waiting"
    sent = world.body(world.calls_to("/internal/logic/games")[0])
    assert sent["mode"] == "multiplayer" and sent["visibility"] == "private" and sent["botLevel"] is None
    assert sent["timeControl"] == {"minutes": 10}
    assert sent["participants"] == [{"userId": A, "color": "white"}]
    assert sent["matchId"] == body["matchId"]
    assert world.published() == []  # al crear nadie está conectado: el hub se entera al conectarse


def test_creation_key_and_fingerprint_match_the_original_service(env):
    """Mismos valores que calculaba el servicio Go: los reintentos de una creación anterior siguen siendo
    idempotentes tras el cambio."""
    client, world = env
    create(client, {"creatorColor": "black", "visibility": "shared", "timeControl": {"minutes": 5}}, key="abc.123")
    sent = world.body(world.calls_to("/internal/logic/games")[0])
    assert sent["creationKey"] == hashlib.sha256(f"{A}\nabc.123".encode()).hexdigest()
    canonical = '{"creatorColor":"black","timeControl":{"minutes":5},"visibility":"shared"}'
    assert sent["requestFingerprint"] == hashlib.sha256(canonical.encode()).hexdigest()
    # el pedido por omisión se calcula con los valores por omisión ya aplicados
    create(client, {"creatorColor": "white"}, key="def")
    default = '{"creatorColor":"white","timeControl":{"minutes":10},"visibility":"private"}'
    assert world.body(world.calls_to("/internal/logic/games")[1])["requestFingerprint"] == hashlib.sha256(default.encode()).hexdigest()


def test_same_idempotency_key_returns_the_original_invitation_and_flags_the_replay(env):
    client, world = env
    first = create(client, key="same").json()
    r = create(client, key="same")
    assert r.status_code == 201 and r.headers["idempotency-replayed"] == "true"
    assert r.json() == first
    assert len(world.games) == 1


def test_reusing_a_key_with_a_different_request_is_idempotency_key_reused(env):
    client, world = env
    create(client, {"creatorColor": "white"}, key="same")
    r = create(client, {"creatorColor": "black"}, key="same")
    assert r.status_code == 409 and code(r) == "IDEMPOTENCY_KEY_REUSED"


def test_the_same_key_from_another_user_is_a_different_creation(env):
    client, world = env
    a = create(client, key="same").json()["matchId"]
    as_user(client, B)
    b = create(client, key="same").json()["matchId"]
    assert a != b and len(world.games) == 2


@pytest.mark.parametrize("key", [None, "", "con espacio", "x" * 129, "a/b", "a;b"])
def test_invalid_idempotency_key_is_a_validation_error_without_calling_logic(env, key):
    client, world = env
    r = create(client, key=key)
    assert r.status_code == 400 and code(r) == "VALIDATION_ERROR"
    assert "Idempotency-Key" in r.json()["error"]["message"] and world.calls == []


@pytest.mark.parametrize("key", ["a", "x" * 128, "A-z_0.9:1"])
def test_valid_idempotency_keys(env, key):
    client, world = env
    assert create(client, key=key).status_code == 201


@pytest.mark.parametrize("body, message", [
    ({}, "creatorColor must be white or black"),
    ({"creatorColor": "green"}, "creatorColor must be white or black"),
    ({"creatorColor": None}, "creatorColor must be white or black"),
    ({"creatorColor": "white", "visibility": "public"}, "visibility must be private or shared"),
    ({"creatorColor": "white", "timeControl": {"minutes": 0}}, "timeControl.minutes must be between 1 and 10"),
    ({"creatorColor": "white", "timeControl": {"minutes": 11}}, "timeControl.minutes must be between 1 and 10"),
    ({"creatorColor": "white", "timeControl": {}}, "timeControl.minutes must be between 1 and 10"),
    ({"creatorColor": "white", "timeControl": {"minutes": None}}, "timeControl.minutes must be between 1 and 10"),
])
def test_invalid_creation_requests_are_validation_errors(env, body, message):
    client, world = env
    r = create(client, body)
    assert r.status_code == 400 and code(r) == "VALIDATION_ERROR" and r.json()["error"]["message"] == message
    assert world.calls == []


@pytest.mark.parametrize("body", [
    {"creatorColor": 5}, {"creatorColor": "white", "visibility": 5}, {"creatorColor": "white", "extra": 1},
    {"creatorColor": "white", "timeControl": 10}, {"creatorColor": "white", "timeControl": {"minutes": "5"}},
    {"creatorColor": "white", "timeControl": {"minutes": 5.5}}, {"creatorColor": "white", "timeControl": {"minutes": True}},
    {"creatorColor": "white", "timeControl": {"minutes": 5, "extra": 1}}, [1],
])
def test_malformed_bodies_are_invalid_json_request_body(env, body):
    client, world = env
    r = create(client, body)
    assert r.status_code == 400 and r.json()["error"]["message"] == "Invalid JSON request body"
    assert world.calls == []


@pytest.mark.parametrize("raw", [b"", b"no es json", b'{"creatorColor":"white"} {"x":1}'])
def test_unparsable_bodies_are_invalid_json_request_body(env, raw):
    client, world = env
    r = client.post("/matches", content=raw, headers={"Idempotency-Key": "k", "Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["message"] == "Invalid JSON request body"


def test_time_control_accepts_1_to_10_minutes(env):
    client, world = env
    for minutes, key in ((1, "a"), (10, "b")):
        assert create(client, {"creatorColor": "white", "timeControl": {"minutes": minutes}}, key=key).status_code == 201
    assert [world.body(c)["timeControl"] for c in world.calls_to("/internal/logic/games")] == [{"minutes": 1}, {"minutes": 10}]


@pytest.mark.parametrize("state, message", [
    ({"mode": "local"}, "Game Logic returned a non-multiplayer game"),
    ({"createdAt": None}, "Game Logic returned an incomplete create response"),
])
def test_unexpected_create_responses_are_bad_gateway(env, state, message):
    client, world = env
    original = world.logic
    world.logic = lambda m, p, b: (
        httpx.Response(201, json={**original(m, p, b).json(), **state}) if (m, p) == ("POST", "/internal/logic/games") else original(m, p, b)
    )
    r = create(client)
    assert r.status_code == 502 and code(r) == "UPSTREAM_ERROR" and r.json()["error"]["message"] == message


def test_create_requires_a_session(env):
    client, world = env
    del client.headers["Authorization"]
    assert create(client).status_code == 401 and world.calls == []


# ================================================================== errores de Game Logic


@pytest.mark.parametrize("reply, status, error_code", [
    ((404, {"error": {"code": "GAME_NOT_FOUND", "message": "m"}}), 404, "MATCH_NOT_FOUND"),
    ((409, {"error": {"code": "GAME_NOT_WAITING", "message": "m"}}), 409, "MATCH_NOT_WAITING"),
    ((409, {"error": {"code": "ALREADY_PARTICIPANT", "message": "m"}}), 409, "ALREADY_PARTICIPANT"),
    ((409, {"error": {"code": "IDEMPOTENCY_KEY_REUSED", "message": "m"}}), 409, "IDEMPOTENCY_KEY_REUSED"),
    ((503, {"error": {"code": "OTRO", "message": "m"}}), 503, "SERVICES_UNAVAILABLE"),
    ((502, {}), 503, "SERVICES_UNAVAILABLE"),
    ((504, None), 503, "SERVICES_UNAVAILABLE"),
    ((422, {"error": {"code": "ALGO", "message": "texto"}}), 422, "ALGO"),
    ((500, None), 500, "UPSTREAM_ERROR"),
    ((400, {"error": {"code": "VALIDATION_ERROR", "message": "texto"}}), 400, "VALIDATION_ERROR"),
])
def test_game_logic_errors_are_mapped_like_the_original_service(env, reply, status, error_code):
    client, world = env
    world.logic_error = reply
    r = create(client)
    assert r.status_code == status and code(r) == error_code
    assert world.published() == []


@pytest.mark.parametrize("failure", [httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_game_logic_unreachable_is_services_unavailable(env, failure):
    client, world = env

    async def boom(request):
        raise failure

    app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    r = create(client)
    assert r.status_code == 503 and code(r) == "SERVICES_UNAVAILABLE" and r.json()["error"]["message"] == "Game Logic is unavailable"


def test_a_non_game_state_response_is_services_unavailable(env):
    client, world = env
    world.logic = lambda m, p, b: httpx.Response(200, json={"algo": "raro"})
    r = client.get(f"/matches/{MATCH}")
    assert r.status_code == 503 and code(r) == "SERVICES_UNAVAILABLE"


# ================================================================== leer


def test_participant_reads_the_match_resolved_by_match_id(env):
    client, world = env
    world.add()
    r = client.get(f"/matches/{MATCH}")
    assert r.status_code == 200 and r.json()["matchId"] == MATCH
    assert [c.url.path for c in world.calls] == [f"/internal/logic/games/by-match/{MATCH}"]
    assert all("x-user-id" not in c.headers for c in world.calls)


def test_non_participants_cannot_read_a_private_match_but_can_read_a_shared_one(env):
    client, world = env
    world.add()
    as_user(client, B)
    r = client.get(f"/matches/{MATCH}")
    assert r.status_code == 404 and code(r) == "MATCH_NOT_FOUND"
    world.add(visibility="shared")
    assert client.get(f"/matches/{MATCH}").status_code == 200


def test_unknown_match_is_match_not_found(env):
    client, world = env
    r = client.get(f"/matches/{MATCH}")
    assert r.status_code == 404 and code(r) == "MATCH_NOT_FOUND"


def test_a_game_with_another_match_id_is_not_served(env):
    client, world = env
    world.add()
    original = world.logic
    world.logic = lambda m, p, b: httpx.Response(200, json={**world.games[GAME], "matchId": "dddddddd-dddd-4ddd-8ddd-dddddddddddd"})
    r = client.get(f"/matches/{MATCH}")
    assert r.status_code == 404 and code(r) == "MATCH_NOT_FOUND"


def test_malformed_match_ids_never_reach_a_service(env):
    client, world = env
    for method, path in (("get", "/matches/x"), ("post", "/matches/x/join"), ("post", "/matches/x/resign"),
                         ("patch", "/matches/x/visibility")):
        r = getattr(client, method)(path)
        assert r.status_code == 404 and code(r) == "MATCH_NOT_FOUND", path
    assert world.calls == []


# ================================================================== unirse


def test_join_calls_game_logic_and_publishes_the_new_state(env):
    client, world = env
    world.add()
    as_user(client, B)
    r = client.post(f"/matches/{MATCH}/join")
    assert r.status_code == 200 and r.json()["status"] == "in_progress" and len(r.json()["participants"]) == 2
    assert world.body(world.calls_to("/join")[0]) == {"userId": B}
    published = world.published()
    assert len(published) == 1 and published[0]["state"]["version"] == 1 and "gameOver" not in published[0]
    # el hub recibe el aviso en su propia ruta
    assert world.calls_to("/publish")[0].url.path == f"/internal/multiplayer/matches/{MATCH}/publish"


def test_the_creator_cannot_join_their_own_match(env):
    client, world = env
    world.add()
    r = client.post(f"/matches/{MATCH}/join")
    assert r.status_code == 409 and code(r) == "ALREADY_PARTICIPANT"
    assert world.calls_to("/join") == [] and world.published() == []


@pytest.mark.parametrize("status", ["in_progress", "finished"])
def test_joining_a_match_that_is_not_waiting_is_match_not_waiting(env, status):
    client, world = env
    world.add(status=status, participants=[{"userId": A, "color": "white"}, {"userId": C, "color": "black"}])
    as_user(client, B)
    r = client.post(f"/matches/{MATCH}/join")
    assert r.status_code == 409 and code(r) == "MATCH_NOT_WAITING"
    assert world.calls_to("/join") == []


def test_two_rivals_joining_at_once_only_one_succeeds(env):
    client, world = env
    world.add()
    as_user(client, B)
    first = client.post(f"/matches/{MATCH}/join")
    as_user(client, C)
    second = client.post(f"/matches/{MATCH}/join")
    assert (first.status_code, second.status_code) == (200, 409) and code(second) == "MATCH_NOT_WAITING"


# ================================================================== rendirse


def test_resign_uses_the_participants_side_and_publishes_state_with_game_over(env):
    client, world = env
    world.add(status="in_progress", participants=[{"userId": A, "color": "white"}, {"userId": B, "color": "black"}], version=3)
    as_user(client, B)
    r = client.post(f"/matches/{MATCH}/resign")
    assert r.status_code == 200 and r.json()["status"] == "finished" and r.json()["result"] == "1-0"
    assert world.body(world.calls_to("/resign")[0]) == {"side": "black"}
    published = world.published()
    assert len(published) == 1 and published[0]["state"]["status"] == "finished" and "gameOver" not in published[0]


def test_resign_by_a_non_participant_is_match_not_found(env):
    client, world = env
    world.add(status="in_progress")
    as_user(client, C)
    r = client.post(f"/matches/{MATCH}/resign")
    assert r.status_code == 404 and code(r) == "MATCH_NOT_FOUND" and world.calls_to("/resign") == []


@pytest.mark.parametrize("status", ["waiting", "finished"])
def test_resign_when_the_game_is_not_in_progress_is_a_conflict(env, status):
    client, world = env
    world.add(status=status)
    r = client.post(f"/matches/{MATCH}/resign")
    assert r.status_code == 409 and code(r) == "GAME_NOT_IN_PROGRESS" and world.calls_to("/resign") == []


@pytest.mark.parametrize("logic_code, http_status", [("GAME_FINISHED", 422), ("VERSION_CONFLICT", 409), ("CLOCK_EXPIRED", 422)])
def test_a_resign_that_races_with_a_finish_refreshes_and_publishes_the_real_state(env, logic_code, http_status):
    client, world = env
    world.add(status="in_progress", participants=[{"userId": A, "color": "white"}, {"userId": B, "color": "black"}])
    original = world.logic

    def raced(method, path, body):
        if path.endswith("/resign"):
            world.games[GAME].update(status="finished", result="1-0", endReason="timeout", version=9)
            return httpx.Response(http_status, json={"error": {"code": logic_code, "message": "perdiste la carrera"}})
        return original(method, path, body)

    world.logic = raced
    r = client.post(f"/matches/{MATCH}/resign")
    assert r.status_code == http_status and code(r) == logic_code
    published = world.published()
    assert len(published) == 1 and published[0]["state"]["status"] == "finished" and published[0]["state"]["version"] == 9


def test_other_logic_errors_on_resign_do_not_publish(env):
    client, world = env
    world.add(status="in_progress")
    original = world.logic
    world.logic = lambda m, p, b: (
        httpx.Response(422, json={"error": {"code": "ALGO", "message": "x"}}) if p.endswith("/resign") else original(m, p, b)
    )
    r = client.post(f"/matches/{MATCH}/resign")
    assert r.status_code == 422 and code(r) == "ALGO" and world.published() == []


# ================================================================== visibilidad


def test_visibility_is_forwarded_with_the_expected_version_and_published_without_game_over(env):
    client, world = env
    world.add(version=4)
    r = client.patch(f"/matches/{MATCH}/visibility", json={"visibility": "shared", "expectedVersion": 4})
    assert r.status_code == 200 and r.json()["visibility"] == "shared" and r.json()["version"] == 5
    assert world.body(world.calls_to("/visibility")[0]) == {"visibility": "shared", "expectedVersion": 4}
    assert world.published()[0]["gameOver"] is False


@pytest.mark.parametrize("body", [{}, {"visibility": "shared"}, {"expectedVersion": 1}, {"visibility": "shared", "expectedVersion": "1"},
                                  {"visibility": "shared", "expectedVersion": 1.5}, {"visibility": 5, "expectedVersion": 1},
                                  {"visibility": "shared", "expectedVersion": 1, "extra": 1}, [1]])
def test_visibility_requires_both_fields(env, body):
    client, world = env
    r = client.patch(f"/matches/{MATCH}/visibility", json=body)
    assert r.status_code == 400 and code(r) == "VALIDATION_ERROR"
    assert world.calls == []


def test_visibility_value_is_validated_before_loading_the_match(env):
    client, world = env
    r = client.patch(f"/matches/{MATCH}/visibility", json={"visibility": "public", "expectedVersion": 1})
    assert r.status_code == 400 and r.json()["error"]["message"] == "visibility must be private or shared"
    assert world.calls == []


def test_only_participants_may_change_the_visibility(env):
    client, world = env
    world.add(version=1)
    as_user(client, B)
    r = client.patch(f"/matches/{MATCH}/visibility", json={"visibility": "shared", "expectedVersion": 1})
    assert r.status_code == 404 and code(r) == "MATCH_NOT_FOUND" and world.calls_to("/visibility") == []


def test_visibility_version_conflict_is_propagated_and_the_state_is_refreshed(env):
    client, world = env
    world.add(version=4)
    r = client.patch(f"/matches/{MATCH}/visibility", json={"visibility": "shared", "expectedVersion": 3})
    assert r.status_code == 409 and code(r) == "VERSION_CONFLICT"
    published = world.published()  # tras un VERSION_CONFLICT se publica el estado vigente
    assert len(published) == 1 and published[0]["state"]["version"] == 4


# ================================================================== resiliencia y concurrencia


def test_a_hub_that_is_down_never_fails_the_request(env):
    client, world = env
    world.add()
    world.hub_down = True
    as_user(client, B)
    r = client.post(f"/matches/{MATCH}/join")
    assert r.status_code == 200 and r.json()["status"] == "in_progress"


def test_the_lock_of_a_finished_match_is_released(env):
    client, world = env
    world.add(status="in_progress")
    client.post(f"/matches/{MATCH}/resign")
    assert "match:" + MATCH not in app.state.locks._locks


def test_operations_on_the_same_match_are_serialized():
    world = World()
    world.delay = 0.03
    world.add(version=0, participants=[{"userId": A, "color": "white"}, {"userId": B, "color": "black"}], status="in_progress")

    def vis(expected):
        body = json.dumps({"visibility": "shared", "expectedVersion": expected}).encode()
        return lambda ctx: multiplayer.change_visibility(ctx, A, MATCH, body)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(world.handler)) as client:
            ctx = Ctx(client=client, upstreams={"logic": "http://logic", "multiplayer": "http://mp"}, locks=GameLocks(), timeout=5)
            return await asyncio.gather(vis(0)(ctx), vis(1)(ctx))

    results = asyncio.run(go())
    # sin lock, el segundo leería la version 0 y su PATCH con expectedVersion 1 daría VERSION_CONFLICT
    assert [r["version"] for r in results] == [1, 2]
