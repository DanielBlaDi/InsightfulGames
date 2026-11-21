"""Saga de borrado de cuenta del gateway móvil (copia propia, sin depender del gateway web)."""

import asyncio
import os
import sys
import time

os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["HTTP_TIMEOUT"] = "2"

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

import main

UID = "11111111-1111-4111-8111-111111111111"
EXISTS = ("GET", f"/internal/auth/users/{UID}")
LOGIC = ("DELETE", f"/internal/logic/users/{UID}")
TUTOR_GAMES = ("GET", f"/internal/tutor/users/{UID}/game-ids")
TUTOR_ERASE = ("POST", f"/internal/tutor/users/{UID}/erase")
PROFILE = ("DELETE", f"/internal/profile/users/{UID}")
ROW = ("DELETE", "/internal/auth/account")
ORDER = [EXISTS, LOGIC, TUTOR_GAMES, TUTOR_ERASE, PROFILE, ROW]


def bearer():
    token = jwt.encode({"sub": UID, "exp": int(time.time()) + 3600}, main.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


class Services:
    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.replies = {EXISTS: 200, LOGIC: 204, TUTOR_GAMES: 200, TUTOR_ERASE: 204, PROFILE: 204, ROW: 204}
        self.delay = 0.0

    def set(self, key, reply):
        self.replies[key] = reply

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        reply = self.replies.get((request.method, request.url.path), 500)
        if isinstance(reply, Exception):
            raise reply
        if reply == 200:
            if request.url.path.endswith("/game-ids"):
                return httpx.Response(200, json={"gameIds": []})
            return httpx.Response(200, json={"userId": UID, "username": "ana"})
        return httpx.Response(reply)

    @property
    def keys(self):
        return [(c.method, c.url.path) for c in self.calls]


@pytest.fixture()
def env():
    services = Services()
    with TestClient(main.app) as client:
        main.app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(services.handler))
        yield client, services


def test_full_saga_in_order_and_each_service_on_its_own_host(env):
    client, services = env
    r = client.delete("/auth/account", headers=bearer())
    assert r.status_code == 204 and r.content == b""
    assert services.keys == ORDER
    hosts = [c.url.host for c in services.calls]
    assert hosts == ["auth-component", "game-logic-component", "tutor-component", "tutor-component",
                     "profile-stats-component", "auth-component"]
    assert "set-cookie" not in r.headers  # el móvil no usa cookies


def test_only_the_final_row_deletion_carries_the_user_id(env):
    client, services = env
    client.delete("/auth/account", headers={**bearer(), "X-User-Id": "99999999-9999-4999-8999-999999999999"})
    carried = {(c.method, c.url.path): c.headers.get("x-user-id") for c in services.calls}
    assert carried[ROW] == UID
    assert [carried[k] for k in (EXISTS, LOGIC, TUTOR_GAMES, TUTOR_ERASE, PROFILE)] == [None] * 5


@pytest.mark.parametrize("failing, name", [(LOGIC, "Game Logic"), (TUTOR_ERASE, "Tutor"), (PROFILE, "Profile/Stats")])
@pytest.mark.parametrize("reply", [503, 404, 500, 200, httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_a_failing_dependency_stops_the_chain_and_keeps_the_account(env, failing, name, reply):
    client, services = env
    services.set(failing, reply)
    r = client.delete("/auth/account", headers=bearer())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SERVICES_UNAVAILABLE"
    assert name in r.json()["error"]["message"]
    assert services.keys == ORDER[: ORDER.index(failing) + 1]
    assert ROW not in services.keys


@pytest.mark.parametrize("reply", [503, 404, 204, httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_tutor_listing_failure_stops_before_any_mutation_in_the_tutor(env, reply):
    client, services = env
    services.set(TUTOR_GAMES, reply)
    r = client.delete("/auth/account", headers=bearer())
    assert r.status_code == 503 and "Tutor" in r.json()["error"]["message"]
    assert services.keys == [EXISTS, LOGIC, TUTOR_GAMES]


def test_retry_after_a_partial_failure_repeats_the_whole_chain(env):
    client, services = env
    services.set(TUTOR_ERASE, 503)
    assert client.delete("/auth/account", headers=bearer()).status_code == 503
    services.calls.clear()
    services.set(TUTOR_ERASE, 204)
    assert client.delete("/auth/account", headers=bearer()).status_code == 204
    assert services.keys == ORDER


def test_user_already_deleted_is_204_without_calling_anyone_else(env):
    client, services = env
    services.set(EXISTS, 404)
    assert client.delete("/auth/account", headers=bearer()).status_code == 204
    assert services.keys == [EXISTS]


@pytest.mark.parametrize("reply", [500, 503, httpx.ConnectError("caído")])
def test_existence_check_failure_stops_before_any_deletion(env, reply):
    client, services = env
    services.set(EXISTS, reply)
    r = client.delete("/auth/account", headers=bearer())
    assert r.status_code == 503 and "Auth" in r.json()["error"]["message"]
    assert services.keys == [EXISTS]


@pytest.mark.parametrize("reply", [500, 503, 200, httpx.ConnectError("caído")])
def test_row_deletion_failure_is_503(env, reply):
    client, services = env
    services.set(ROW, reply)
    r = client.delete("/auth/account", headers=bearer())
    assert r.status_code == 503 and "Auth" in r.json()["error"]["message"]
    assert services.keys == ORDER


def test_the_whole_saga_has_a_deadline(env, monkeypatch):
    client, services = env
    monkeypatch.setattr(main, "HTTP_TIMEOUT", 0.05)
    services.delay = 1.0
    r = client.delete("/auth/account", headers=bearer())
    assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICES_UNAVAILABLE"
    assert ROW not in services.keys


def test_requires_a_bearer_token_and_never_calls_services_without_one(env):
    client, services = env
    r = client.delete("/auth/account")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
    assert services.calls == []


# --------------------------------------- paso del Tutor: visibilidad actual de cada partida

G1, G2, G3 = (f"{c * 8}-{c * 4}-4{c * 3}-8{c * 3}-{c * 12}" for c in "abc")


class TutorServices(Services):
    """Añade Game Logic (GET partidas) a los servicios falsos."""

    def __init__(self):
        super().__init__()
        self.games: dict = {}
        self.replies[TUTOR_GAMES] = 200
        self.game_ids = [G1, G2, G3]

    async def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.startswith("/internal/logic/games/"):
            self.calls.append(request)
            entry = self.games.get(path.rsplit("/", 1)[-1], 404)
            if isinstance(entry, Exception):
                raise entry
            if isinstance(entry, int):
                return httpx.Response(entry, json={})
            return httpx.Response(200, json=entry)
        if request.method == "GET" and path.endswith("/game-ids"):
            self.calls.append(request)
            return httpx.Response(200, json={"gameIds": self.game_ids})
        return await super().handler(request)


@pytest.fixture()
def tutor_env():
    services = TutorServices()
    with TestClient(main.app) as client:
        main.app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(services.handler))
        yield client, services


def erase_body(services):
    import json
    return json.loads(next(c for c in services.calls if c.method == "POST").content)


def test_only_shared_games_are_kept_everything_else_is_erased(tutor_env):
    client, s = tutor_env
    s.games[G1] = {"visibility": "private"}
    s.games[G2] = {"visibility": "shared"}  # G3: 404 en Game Logic -> se borra
    assert client.delete("/auth/account", headers=bearer()).status_code == 204
    assert erase_body(s) == {"keepGameIds": [G2]}


@pytest.mark.parametrize("visibility", [None, "public", "", "private", 5])
def test_unexpected_visibility_is_treated_as_private_fail_closed(tutor_env, visibility):
    client, s = tutor_env
    s.games.update({G1: {"visibility": visibility}, G2: {"visibility": "shared"}, G3: {}})
    assert client.delete("/auth/account", headers=bearer()).status_code == 204
    assert erase_body(s) == {"keepGameIds": [G2]}


@pytest.mark.parametrize("bad", [503, 500, httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_a_game_logic_failure_aborts_before_any_mutation_in_the_tutor(tutor_env, bad):
    client, s = tutor_env
    s.games.update({G1: {"visibility": "shared"}, G2: bad, G3: {"visibility": "private"}})
    r = client.delete("/auth/account", headers=bearer())
    assert r.status_code == 503 and "Game Logic" in r.json()["error"]["message"]
    assert all(c.method != "POST" for c in s.calls)
    assert ROW not in s.keys and PROFILE not in s.keys


def test_resolution_of_all_games_happens_before_the_tutor_is_mutated(tutor_env):
    client, s = tutor_env
    s.games.update({G1: {"visibility": "shared"}, G2: {"visibility": "private"}, G3: {"visibility": "shared"}})
    assert client.delete("/auth/account", headers=bearer()).status_code == 204
    post = next(i for i, c in enumerate(s.calls) if c.method == "POST")
    reads = [i for i, c in enumerate(s.calls) if c.url.path.startswith("/internal/logic/games/")]
    assert len(reads) == 3 and max(reads) < post
