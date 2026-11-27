import asyncio
import os
import time

os.environ.update(JWT_SECRET="x" * 40, WS_ALLOWED_ORIGINS="http://localhost")

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

import main
from main import app

UID = "11111111-1111-4111-8111-111111111111"
TOKEN = jwt.encode({"sub": UID, "exp": int(time.time()) + 60}, "x" * 40, algorithm="HS256")

EXISTS = ("GET", f"/internal/auth/users/{UID}")
LOGIC = ("DELETE", f"/internal/logic/users/{UID}")
TUTOR_GAMES = ("GET", f"/internal/tutor/users/{UID}/game-ids")
TUTOR_ERASE = ("POST", f"/internal/tutor/users/{UID}/erase")
PROFILE = ("DELETE", f"/internal/profile/users/{UID}")
ROW = ("DELETE", "/internal/auth/account")
ORDER = [EXISTS, LOGIC, TUTOR_GAMES, TUTOR_ERASE, PROFILE, ROW]


class Services:
    """Servicios falsos: responden según (método, ruta) y registran el orden de las llamadas."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.replies: dict[tuple[str, str], object] = {
            EXISTS: 200, LOGIC: 204, TUTOR_GAMES: 200, TUTOR_ERASE: 204, PROFILE: 204, ROW: 204,
        }
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


@pytest.fixture
def env():
    services = Services()
    with TestClient(app) as client:
        app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(services.handler))
        client.cookies.set("session", TOKEN)
        yield client, services


def test_full_saga_runs_in_the_mandatory_order_and_clears_the_cookie(env):
    client, services = env
    r = client.delete("/auth/account")
    assert r.status_code == 204
    assert services.keys == ORDER
    assert "session=" in r.headers["set-cookie"].lower() and "max-age=0" in r.headers["set-cookie"].lower()


def test_only_the_final_row_deletion_carries_the_user_id(env):
    client, services = env
    client.delete("/auth/account")
    carried = {(c.method, c.url.path): c.headers.get("x-user-id") for c in services.calls}
    assert carried[ROW] == UID
    assert [carried[k] for k in (EXISTS, LOGIC, TUTOR_GAMES, TUTOR_ERASE, PROFILE)] == [None] * 5


@pytest.mark.parametrize("failing, name, ok_reply", [
    (LOGIC, "Game Logic", 204),
    (TUTOR_ERASE, "Tutor", 204),
    (PROFILE, "Profile/Stats", 204),
])
@pytest.mark.parametrize("reply", [503, 404, 500, 200, httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_a_failing_dependency_stops_the_chain_and_keeps_the_account(env, failing, name, ok_reply, reply):
    client, services = env
    services.set(failing, reply)
    r = client.delete("/auth/account")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SERVICES_UNAVAILABLE"
    assert name in r.json()["error"]["message"]
    # se llamó hasta la que falló, en orden, y ninguna posterior; la fila de Auth no se toca
    expected = ORDER[: ORDER.index(failing) + 1]
    assert services.keys == expected
    assert ROW not in services.keys
    assert "set-cookie" not in r.headers  # la sesión sigue viva para poder reintentar


@pytest.mark.parametrize("reply", [503, 404, 204, httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_tutor_listing_failure_stops_before_any_mutation_in_the_tutor(env, reply):
    client, services = env
    services.set(TUTOR_GAMES, reply)
    r = client.delete("/auth/account")
    assert r.status_code == 503 and "Tutor" in r.json()["error"]["message"]
    assert services.keys == [EXISTS, LOGIC, TUTOR_GAMES]
    assert TUTOR_ERASE not in services.keys and ROW not in services.keys


def test_retry_after_a_partial_failure_repeats_the_whole_chain(env):
    client, services = env
    services.set(TUTOR_ERASE, 503)
    assert client.delete("/auth/account").status_code == 503
    services.calls.clear()
    services.set(TUTOR_ERASE, 204)
    assert client.delete("/auth/account").status_code == 204
    assert services.keys == ORDER


def test_user_already_deleted_is_204_without_calling_anyone_else(env):
    client, services = env
    services.set(EXISTS, 404)
    r = client.delete("/auth/account")
    assert r.status_code == 204
    assert services.keys == [EXISTS]
    assert "max-age=0" in r.headers["set-cookie"].lower()


@pytest.mark.parametrize("reply", [500, 503, httpx.ConnectError("caído")])
def test_existence_check_failure_stops_before_any_deletion(env, reply):
    client, services = env
    services.set(EXISTS, reply)
    r = client.delete("/auth/account")
    assert r.status_code == 503 and "Auth" in r.json()["error"]["message"]
    assert services.keys == [EXISTS]


@pytest.mark.parametrize("reply", [500, 503, 200, httpx.ConnectError("caído")])
def test_row_deletion_failure_is_503_and_keeps_the_session(env, reply):
    client, services = env
    services.set(ROW, reply)
    r = client.delete("/auth/account")
    assert r.status_code == 503 and "Auth" in r.json()["error"]["message"]
    assert services.keys == ORDER
    assert "set-cookie" not in r.headers


def test_the_whole_saga_has_a_deadline(env, monkeypatch):
    client, services = env
    monkeypatch.setattr(main, "HTTP_TIMEOUT", 0.05)
    services.delay = 1.0
    r = client.delete("/auth/account")
    assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICES_UNAVAILABLE"
    assert ROW not in services.keys


def test_requires_a_session_and_never_calls_services_without_one(env):
    client, services = env
    client.cookies.clear()
    r = client.delete("/auth/account")
    assert r.status_code == 401
    assert services.calls == []


def test_client_supplied_user_id_is_ignored(env):
    client, services = env
    client.delete("/auth/account", headers={"X-User-Id": "99999999-9999-4999-8999-999999999999"})
    assert all("99999999" not in str(c.url) for c in services.calls)
    assert ROW in services.keys and services.calls[-1].headers["x-user-id"] == UID
