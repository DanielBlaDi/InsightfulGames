"""Flows del Tutor en el gateway web: el gateway lee Game Logic y decide la visibilidad."""

import os
import time

os.environ.update(JWT_SECRET="x" * 40, WS_ALLOWED_ORIGINS="http://localhost")

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from main import app

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
C = "33333333-3333-4333-8333-333333333333"
G1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
G2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
G3 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
AN = "99999999-9999-4999-8999-999999999999"


def token(user):
    return jwt.encode({"sub": user, "exp": int(time.time()) + 60}, "x" * 40, algorithm="HS256")


def game(game_id=G1, *, visibility="private", users=(A,), status="finished", end_reason="checkmate", moves=2):
    return {
        "gameId": game_id, "visibility": visibility, "status": status, "endReason": end_reason,
        "participants": [{"userId": u, "color": "white" if i == 0 else "black"} for i, u in enumerate(users)],
        "moves": [{"ply": i + 1} for i in range(moves)], "fen": "no-se-reenvia",
    }


class Services:
    """Game Logic y Tutor falsos: registran las llamadas y responden según los mapas."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.games: dict[str, object] = {}  # id -> dict | int (estado de error) | Exception
        self.tutor: dict[tuple[str, str], object] = {}  # (método, ruta) -> (estado, json) | Exception

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if path.startswith("/internal/logic/games/"):
            entry = self.games.get(path.rsplit("/", 1)[-1], 404)
            if isinstance(entry, Exception):
                raise entry
            if isinstance(entry, int):
                return httpx.Response(entry, json={"error": {"code": "GAME_NOT_FOUND", "message": "x"}} if entry == 404 else {})
            return httpx.Response(200, json=entry)
        if path.startswith("/internal/tutor/"):
            entry = self.tutor.get((request.method, path), (500, {}))
            if isinstance(entry, Exception):
                raise entry
            status, body = entry
            return httpx.Response(status, json=body) if body is not None else httpx.Response(status)
        return httpx.Response(500)

    def tutor_calls(self):
        return [c for c in self.calls if c.url.path.startswith("/internal/tutor/")]

    def logic_calls(self):
        return [c for c in self.calls if c.url.path.startswith("/internal/logic/")]


@pytest.fixture
def env():
    services = Services()
    with TestClient(app) as client:
        app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(services.handler))
        client.headers["Authorization"] = f"Bearer {token(A)}"
        yield client, services


def as_user(client, user):
    client.headers["Authorization"] = f"Bearer {token(user)}"


ANALYSIS = {"analysisId": "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "gameId": G1, "status": "pending"}
POST = ("POST", "/internal/tutor/analyses")


# ----------------------------------------------------------------------- crear


def test_create_reads_game_logic_then_posts_a_snapshot_with_the_user_id(env):
    client, s = env
    s.games[G1] = game(users=(A, B))
    s.tutor[POST] = (202, ANALYSIS)

    r = client.post("/tutor/analyses", json={"gameId": G1, "depth": 12, "language": "en", "detailLevel": "brief"})

    assert r.status_code == 202 and r.json()["analysisId"] == ANALYSIS["analysisId"]
    assert [c.url.path for c in s.calls] == [f"/internal/logic/games/{G1}", "/internal/tutor/analyses"]
    sent = s.tutor_calls()[0]
    assert sent.headers["x-user-id"] == A
    import json
    body = json.loads(sent.content)
    assert body == {
        "gameId": G1, "depth": 12, "language": "en", "detailLevel": "brief",
        "game": {"status": "finished", "endReason": "checkmate", "moveCount": 2, "participantIds": [A, B]},
    }


def test_create_analysis_rate_limit_returns_429_without_reaching_services(env):
    client, s = env
    s.games[G1] = game(users=(A,))
    s.tutor[POST] = (202, ANALYSIS)
    app.state.rate_limiter = app.state.rate_limiter.__class__(max_requests=5, window_seconds=60)

    for _ in range(5):
        assert client.post("/tutor/analyses", json={"gameId": G1}).status_code == 202

    blocked = client.post("/tutor/analyses", json={"gameId": G1})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert len(s.tutor_calls()) == 5



def test_snapshot_is_rebuilt_from_validated_fields_never_a_copy_of_the_game(env):
    client, s = env
    s.games[G1] = game(users=(A, A))
    s.tutor[POST] = (202, ANALYSIS)
    client.post("/tutor/analyses", json={"gameId": G1})
    import json
    sent = json.loads(s.tutor_calls()[0].content)
    assert set(sent["game"]) == {"status", "endReason", "moveCount", "participantIds"}
    assert sent["game"]["participantIds"] == [A]  # sin repetir (local: ambos colores)
    assert "fen" not in sent["game"] and "moves" not in sent["game"]


def test_client_cannot_inject_the_game_snapshot_or_other_fields(env):
    client, s = env
    s.games[G1] = game(status="in_progress", moves=0)
    s.tutor[POST] = (409, {"error": {"code": "GAME_NOT_FINISHED", "message": "x"}})
    fake = {"status": "finished", "endReason": "checkmate", "moveCount": 99, "participantIds": [A]}
    client.post("/tutor/analyses", json={"gameId": G1, "game": fake, "requestedBy": B, "extra": 1})
    import json
    sent = json.loads(s.tutor_calls()[0].content)
    assert sent["game"]["status"] == "in_progress" and sent["game"]["moveCount"] == 0
    assert set(sent) == {"gameId", "game"}


def test_tutor_domain_errors_pass_through(env):
    client, s = env
    s.games[G1] = game(status="in_progress")
    s.tutor[POST] = (409, {"error": {"code": "GAME_NOT_FINISHED", "message": "La partida debe estar terminada"}})
    r = client.post("/tutor/analyses", json={"gameId": G1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "GAME_NOT_FINISHED"


def test_create_200_for_an_existing_analysis_passes_through(env):
    client, s = env
    s.games[G1] = game()
    s.tutor[POST] = (200, ANALYSIS)
    assert client.post("/tutor/analyses", json={"gameId": G1}).status_code == 200


def test_private_game_of_another_user_is_game_not_found_and_never_reaches_the_tutor(env):
    client, s = env
    s.games[G1] = game(users=(A,))
    as_user(client, C)
    r = client.post("/tutor/analyses", json={"gameId": G1})
    assert r.status_code == 404 and r.json()["error"]["code"] == "GAME_NOT_FOUND"
    assert s.tutor_calls() == []


def test_participant_of_a_private_game_and_anyone_on_a_shared_game_can_request(env):
    client, s = env
    s.games[G1] = game(users=(A, B))
    s.games[G2] = game(G2, visibility="shared", users=(A,))
    s.tutor[POST] = (202, ANALYSIS)
    as_user(client, B)
    assert client.post("/tutor/analyses", json={"gameId": G1}).status_code == 202
    as_user(client, C)
    assert client.post("/tutor/analyses", json={"gameId": G2}).status_code == 202


@pytest.mark.parametrize("visibility", [None, "public", "", 5])
def test_unknown_visibility_is_not_visible_fail_closed(env, visibility):
    client, s = env
    g = game(users=(A,))
    g["visibility"] = visibility
    s.games[G1] = g
    r = client.post("/tutor/analyses", json={"gameId": G1})
    assert r.status_code == 404 and r.json()["error"]["code"] == "GAME_NOT_FOUND"
    assert s.tutor_calls() == []


def test_unknown_game_is_game_not_found(env):
    client, s = env
    r = client.post("/tutor/analyses", json={"gameId": G3})
    assert r.status_code == 404 and r.json()["error"]["code"] == "GAME_NOT_FOUND"
    assert s.tutor_calls() == []


@pytest.mark.parametrize("entry", [503, 500, httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_game_logic_failure_is_503_and_never_reaches_the_tutor(env, entry):
    client, s = env
    s.games[G1] = entry
    r = client.post("/tutor/analyses", json={"gameId": G1})
    assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICES_UNAVAILABLE"
    assert s.tutor_calls() == []


@pytest.mark.parametrize("body", [{}, {"gameId": ""}, {"gameId": 5}, {"gameId": "no-es-uuid"}, [1], "x"])
def test_invalid_game_id_is_validation_error_without_calling_anyone(env, body):
    client, s = env
    r = client.post("/tutor/analyses", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert s.calls == []


def test_malformed_json_is_validation_error(env):
    client, s = env
    r = client.post("/tutor/analyses", content=b"{no es json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert s.calls == []


def test_uppercase_game_id_is_normalized(env):
    client, s = env
    s.games[G1] = game()
    s.tutor[POST] = (202, ANALYSIS)
    assert client.post("/tutor/analyses", json={"gameId": G1.upper()}).status_code == 202
    assert s.logic_calls()[0].url.path == f"/internal/logic/games/{G1}"


def test_create_requires_a_session(env):
    client, s = env
    del client.headers["Authorization"]
    assert client.post("/tutor/analyses", json={"gameId": G1}).status_code == 401
    assert s.calls == []


# ----------------------------------------------------------------------- leer

AID = ANALYSIS["analysisId"]
REF = ("GET", f"/internal/tutor/analyses/{AID}/game-ref")
STATUS = ("GET", f"/internal/tutor/analyses/{AID}")
RESULT = ("GET", f"/internal/tutor/analyses/{AID}/result")


def read_setup(s, g=None):
    s.tutor[REF] = (200, {"gameId": G1})
    s.tutor[STATUS] = (200, {**ANALYSIS, "status": "completed"})
    s.tutor[RESULT] = (200, {"analysisId": AID, "summary": {}})
    s.games[G1] = g if g is not None else game(users=(A,))


def test_read_status_checks_visibility_then_reads(env):
    client, s = env
    read_setup(s)
    r = client.get(f"/tutor/analyses/{AID}")
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert [c.url.path for c in s.calls] == [
        f"/internal/tutor/analyses/{AID}/game-ref", f"/internal/logic/games/{G1}", f"/internal/tutor/analyses/{AID}",
    ]


def test_read_result_uses_the_result_route(env):
    client, s = env
    read_setup(s)
    r = client.get(f"/tutor/analyses/{AID}/result")
    assert r.status_code == 200 and r.json()["analysisId"] == AID
    assert s.calls[-1].url.path == f"/internal/tutor/analyses/{AID}/result"


@pytest.mark.parametrize("suffix", ["", "/result"])
def test_another_user_cannot_read_an_analysis_of_a_private_game(env, suffix):
    client, s = env
    read_setup(s)
    as_user(client, B)
    r = client.get(f"/tutor/analyses/{AID}{suffix}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
    assert ("GET", f"/internal/tutor/analyses/{AID}{suffix}") not in [(c.method, c.url.path) for c in s.calls]


def test_visibility_is_recomputed_on_every_read(env):
    client, s = env
    read_setup(s)
    as_user(client, B)
    assert client.get(f"/tutor/analyses/{AID}").status_code == 404
    s.games[G1] = game(visibility="shared", users=(A,))
    assert client.get(f"/tutor/analyses/{AID}").status_code == 200
    s.games[G1] = game(visibility="private", users=(A,))
    assert client.get(f"/tutor/analyses/{AID}").status_code == 404


def test_if_the_game_disappears_the_analysis_is_not_found(env):
    client, s = env
    read_setup(s)
    del s.games[G1]
    r = client.get(f"/tutor/analyses/{AID}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


@pytest.mark.parametrize("entry", [503, httpx.ConnectError("caído")])
def test_read_with_game_logic_down_is_503(env, entry):
    client, s = env
    read_setup(s)
    s.games[G1] = entry
    r = client.get(f"/tutor/analyses/{AID}")
    assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICES_UNAVAILABLE"


def test_unknown_analysis_is_analysis_not_found_without_reading_game_logic(env):
    client, s = env
    s.tutor[REF] = (404, {"error": {"code": "ANALYSIS_NOT_FOUND", "message": "no existe"}})
    r = client.get(f"/tutor/analyses/{AID}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
    assert s.logic_calls() == []


def test_result_not_ready_passes_through(env):
    client, s = env
    read_setup(s)
    s.tutor[RESULT] = (409, {"error": {"code": "ANALYSIS_NOT_READY", "message": "todavía no"}})
    r = client.get(f"/tutor/analyses/{AID}/result")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ANALYSIS_NOT_READY"


def test_malformed_analysis_id_never_reaches_a_service(env):
    client, s = env
    r = client.get("/tutor/analyses/no-es-uuid")
    assert r.status_code == 404 and r.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
    assert s.calls == []


# ------------------------------------------------------- borrado de cuenta (erase)

LISTING = ("GET", f"/internal/tutor/users/{A}/game-ids")
ERASE = ("POST", f"/internal/tutor/users/{A}/erase")


def erase_account(client):
    """Ejecuta solo el paso del Tutor a través de la saga completa con los demás servicios en 204."""
    return client.delete("/auth/account")


@pytest.fixture
def saga(env):
    client, s = env
    base_handler = s.handler

    def handler(request):
        path = request.url.path
        if request.method == "GET" and path == f"/internal/auth/users/{A}":
            s.calls.append(request)
            return httpx.Response(200, json={"userId": A, "username": "ana"})
        if request.method == "DELETE" and path.startswith(("/internal/logic/users/", "/internal/profile/users/", "/internal/auth/account")):
            s.calls.append(request)
            return httpx.Response(204)
        return base_handler(request)

    app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    s.tutor[LISTING] = (200, {"gameIds": [G1, G2, G3]})
    s.tutor[ERASE] = (204, None)
    return client, s


def erase_body(s):
    import json
    return json.loads(next(c for c in s.tutor_calls() if c.method == "POST").content)


def test_only_shared_games_are_kept_everything_else_is_erased(saga):
    client, s = saga
    s.games[G1] = game(G1, visibility="private")
    s.games[G2] = game(G2, visibility="shared")
    # G3 no existe en Game Logic (404): se borran sus análisis
    assert erase_account(client).status_code == 204
    assert erase_body(s) == {"keepGameIds": [G2]}


def test_visibility_is_resolved_for_every_game_before_the_tutor_is_mutated(saga):
    client, s = saga
    s.games[G1] = game(G1, visibility="shared")
    s.games[G2] = game(G2, visibility="private")
    s.games[G3] = game(G3, visibility="shared")
    assert erase_account(client).status_code == 204
    # la mutación (POST erase) va después de todas las lecturas a Game Logic de las partidas
    posts = [i for i, c in enumerate(s.calls) if c.method == "POST"]
    games_reads = [i for i, c in enumerate(s.calls) if c.url.path.startswith("/internal/logic/games/")]
    assert posts and max(games_reads) < posts[0]


@pytest.mark.parametrize("visibility", [None, "public", "", "private", 5])
def test_any_unexpected_visibility_is_treated_as_private_fail_closed(saga, visibility):
    client, s = saga
    g = game(G1)
    g["visibility"] = visibility
    s.games.update({G1: g, G2: game(G2, visibility="shared"), G3: 404})
    assert erase_account(client).status_code == 204
    assert erase_body(s) == {"keepGameIds": [G2]}


def test_a_game_logic_failure_aborts_before_any_mutation_in_the_tutor(saga):
    client, s = saga
    s.games[G1] = game(G1, visibility="shared")
    s.games[G2] = 503
    s.games[G3] = game(G3, visibility="private")
    r = erase_account(client)
    assert r.status_code == 503 and "Game Logic" in r.json()["error"]["message"]
    assert all(c.method != "POST" for c in s.tutor_calls())
    assert all("/internal/profile/" not in c.url.path and "/internal/auth/account" not in c.url.path for c in s.calls)


@pytest.mark.parametrize("failure", [httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_game_logic_transport_failure_aborts_too(saga, failure):
    client, s = saga
    s.games.update({G1: game(G1), G2: failure, G3: game(G3)})
    r = erase_account(client)
    assert r.status_code == 503 and "Game Logic" in r.json()["error"]["message"]
    assert all(c.method != "POST" for c in s.tutor_calls())


def test_a_user_without_analyses_still_calls_erase_with_an_empty_keep_list(saga):
    client, s = saga
    s.tutor[LISTING] = (200, {"gameIds": []})
    assert erase_account(client).status_code == 204
    assert erase_body(s) == {"keepGameIds": []}
    assert [c for c in s.calls if c.url.path.startswith("/internal/logic/games/")] == []


@pytest.mark.parametrize("listing", [(200, {"gameIds": "x"}), (200, {}), (200, {"gameIds": [1]}), (500, {}), (404, {})])
def test_bad_listing_response_aborts_with_tutor_unavailable(saga, listing):
    client, s = saga
    s.tutor[LISTING] = listing
    r = erase_account(client)
    assert r.status_code == 503 and "Tutor" in r.json()["error"]["message"]
    assert all(c.method != "POST" for c in s.tutor_calls())


def test_many_games_are_resolved_with_bounded_concurrency(saga):
    client, s = saga
    ids = [f"{i:08x}-0000-4000-8000-000000000000" for i in range(40)]
    s.tutor[LISTING] = (200, {"gameIds": ids})
    for i, g in enumerate(ids):
        s.games[g] = game(g, visibility="shared" if i % 2 == 0 else "private")
    assert erase_account(client).status_code == 204
    assert erase_body(s)["keepGameIds"] == ids[::2]
