import os, time
os.environ.update(JWT_SECRET="x" * 40, WS_ALLOWED_ORIGINS="http://localhost")

import httpx, jwt, pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from main import app

UID = "11111111-1111-4111-8111-111111111111"
GID = "22222222-2222-4222-8222-222222222222"
TOKEN = jwt.encode({"sub": UID, "exp": int(time.time()) + 60}, "x" * 40, algorithm="HS256")
calls: list[httpx.Request] = []


def handler(req: httpx.Request) -> httpx.Response:
    calls.append(req)
    if req.url.path == "/internal/auth/login":
        return httpx.Response(200, json={"accessToken": TOKEN, "expiresIn": 3600,
                                         "user": {"userId": UID, "username": "ana"}})
    return httpx.Response(200, json={"ok": True})


@pytest.fixture
def client():
    calls.clear()
    with TestClient(app) as c:
        app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        yield c


def test_login_sets_httponly_cookie(client):
    r = client.post("/auth/login", json={"username": "ana", "password": "12345678"})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_requires_session(client):
    assert client.get("/stats/me").status_code == 401


def test_cookie_and_bearer_work_and_client_user_id_is_ignored(client):
    r = client.get(f"/games/{GID}", headers={"Authorization": f"Bearer {TOKEN}", "X-User-Id": "evil"})
    assert r.status_code == 200
    assert calls[-1].headers["x-user-id"] == UID
    client.cookies.set("session", TOKEN)
    assert client.get("/stats/me").status_code == 200
    assert calls[-1].url.path == f"/internal/profile/users/{UID}/stats"


def test_invalid_id_never_reaches_upstream(client):
    client.cookies.set("session", TOKEN)
    r = client.get("/games/..%2Fadmin")
    assert r.status_code == 404 and not calls


def test_games_list_uses_sub_not_client_userid(client):
    client.cookies.set("session", TOKEN)
    client.get("/games?userId=evil&limit=99")
    q = dict(calls[-1].url.params)
    assert q["userId"] == UID and q["limit"] == "20"


def test_passthrough_keeps_method_query_and_user_id(client):
    client.delete("/internal/logic/users/abc?x=1", headers={"X-User-Id": UID})
    req = calls[-1]
    assert req.method == "DELETE" and req.url.path == "/internal/logic/users/abc"
    assert req.url.params["x"] == "1" and req.headers["x-user-id"] == UID


def test_unknown_internal_service_is_404(client):
    assert client.get("/internal/nada/x").status_code == 404


@pytest.mark.parametrize("origin", ["http://evil.com", "https://localhost", "http://localhost:81", "null"])
def test_ws_bad_origin_closes_4403(client, origin):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/ws/games/{GID}", headers={"origin": origin}) as ws:
            ws.receive_text()
    assert e.value.code == 4403


def test_ws_without_session_closes_4401(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/ws/games/{GID}", headers={"origin": "http://localhost"}) as ws:
            ws.receive_text()
    assert e.value.code == 4401