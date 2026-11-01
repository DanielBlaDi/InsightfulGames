"""Pruebas del gateway móvil contra los contratos v9 (sección 5).
El gateway interno se simula con httpx.MockTransport."""

import os
import sys
import time

os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["GATEWAY_INTERNAL_URL"] = "http://internal.test"
os.environ["HTTP_TIMEOUT"] = "2"

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

import main

USER = "11111111-1111-4111-8111-111111111111"
GAME = "22222222-2222-4222-8222-222222222222"
MATCH = "33333333-3333-4333-8333-333333333333"


def token(sub=USER, exp_in=3600, secret=None, alg="HS256"):
    claims = {"sub": sub, "username": "ana", "exp": int(time.time()) + exp_in}
    return jwt.encode(claims, secret or main.JWT_SECRET, algorithm=alg)


def auth(**kw):
    return {"Authorization": f"Bearer {token(**kw)}"}


class Internal:
    """Gateway interno falso: registra las peticiones y responde según un mapa."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], object] = {}

    def on(self, method, path, status=200, json=None, exc=None):
        self.routes[(method, path)] = (status, json, exc)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        entry = self.routes.get((request.method, request.url.path))
        if entry is None:
            return httpx.Response(500, json={"oops": "ruta no simulada"})
        status, body, exc = entry
        if exc:
            raise exc
        if body is None:
            return httpx.Response(status)
        return httpx.Response(status, json=body)


@pytest.fixture()
def env():
    internal = Internal()
    with TestClient(main.app) as client:
        main.app.state.client = httpx.AsyncClient(
            base_url=main.GATEWAY_INTERNAL_URL,
            transport=httpx.MockTransport(internal.handler),
        )
        yield client, internal


# ---------------------------------------------------------------- seguridad


def test_health(env):
    client, _ = env
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/internal/auth/login", "/internal/logic/games", "/INTERNAL/x", "/internal"])
def test_internal_routes_are_404(env, path):
    client, internal = env
    r = client.get(path, headers=auth())
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert internal.calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer basura"},
        auth(exp_in=-10),
        auth(secret="otra-clave-otra-clave-otra-clave-123"),
        auth(sub="no-es-uuid"),
        auth(sub="../../etc"),
    ],
)
def test_protected_routes_need_valid_bearer(env, headers):
    client, internal = env
    for path in ["/home", "/profile/me", "/stats/me", "/games", f"/games/{GAME}", f"/matches/{MATCH}"]:
        r = client.get(path, headers=headers)
        assert r.status_code == 401, path
        assert r.json()["error"]["code"] == "UNAUTHORIZED"
    assert internal.calls == []


def test_cookie_is_not_accepted(env):
    client, _ = env
    r = client.get("/profile/me", cookies={"session": token()})
    assert r.status_code == 401


def test_client_x_user_id_is_never_forwarded(env):
    client, internal = env
    internal.on("GET", f"/internal/single-player/games/{GAME}", json={"gameId": GAME})
    r = client.get(f"/games/{GAME}", headers={**auth(), "X-User-Id": "99999999-9999-4999-8999-999999999999"})
    assert r.status_code == 200
    assert internal.calls[0].headers["x-user-id"] == USER  # el del JWT, no el del cliente


# --------------------------------------------------------------------- auth


def test_login_passthrough_without_cookie(env):
    client, internal = env
    body = {"accessToken": "jwt", "expiresIn": 3600, "user": {"userId": USER, "username": "ana"}}
    internal.on("POST", "/internal/auth/login", json=body)
    r = client.post("/auth/login", json={"username": "ana", "password": "x"})
    assert r.status_code == 200 and r.json() == body
    assert "set-cookie" not in r.headers


def test_login_invalid_credentials_code(env):
    client, internal = env
    internal.on("POST", "/internal/auth/login", status=401, json={"message": "bad"})
    r = client.post("/auth/login", json={"username": "ana", "password": "x"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_register_ok_and_username_taken(env):
    client, internal = env
    internal.on("POST", "/internal/auth/register", status=201, json={"userId": USER, "username": "ana"})
    r = client.post("/auth/register", json={"username": "ana", "password": "12345678"})
    assert r.status_code == 201 and r.json()["userId"] == USER

    internal.on("POST", "/internal/auth/register", status=409, json={"x": 1})
    r = client.post("/auth/register", json={"username": "ana", "password": "12345678"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "USERNAME_TAKEN"


@pytest.mark.parametrize(
    "body",
    [{"username": "an", "password": "12345678"}, {"username": "ana", "password": "corta"}, {"username": "ana"}],
)
def test_register_validation(env, body):
    client, internal = env
    r = client.post("/auth/register", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert internal.calls == []


# ------------------------------------------------------------ perfil / stats


def test_profile_and_stats_use_userid_from_jwt(env):
    client, internal = env
    internal.on("GET", f"/internal/profile/users/{USER}/profile", json={"userId": USER, "username": "ana"})
    internal.on("GET", f"/internal/profile/users/{USER}/stats", json={"gamesPlayed": 3, "wins": 2, "losses": 1, "draws": 0})
    assert client.get("/profile/me", headers=auth()).json()["username"] == "ana"
    assert client.get("/stats/me", headers=auth()).json()["wins"] == 2


# --------------------------------------------------------------------- games


def test_games_forwards_cursor_and_clamps_limit(env):
    client, internal = env
    internal.on("GET", "/internal/logic/games", json={"items": [], "nextCursor": None})
    r = client.get("/games?limit=500&cursor=abc", headers=auth())
    assert r.status_code == 200
    q = internal.calls[0].url.params
    assert q["userId"] == USER and q["limit"] == "20" and q["cursor"] == "abc"


def test_games_default_limit_and_invalid_limit(env):
    client, internal = env
    internal.on("GET", "/internal/logic/games", json={"items": [], "nextCursor": None})
    client.get("/games", headers=auth())
    assert internal.calls[0].url.params["limit"] == "20"
    assert "cursor" not in internal.calls[0].url.params
    assert client.get("/games?limit=0", headers=auth()).status_code == 400
    assert client.get("/games?limit=abc", headers=auth()).status_code == 400


def test_game_detail_goes_to_single_player(env):
    client, internal = env
    internal.on("GET", f"/internal/single-player/games/{GAME}", json={"gameId": GAME, "mode": "vs_bot"})
    r = client.get(f"/games/{GAME}", headers=auth())
    assert r.status_code == 200 and r.json()["mode"] == "vs_bot"
    assert internal.calls[0].url.path == f"/internal/single-player/games/{GAME}"


def test_match_detail_goes_to_multiplayer(env):
    client, internal = env
    internal.on("GET", f"/internal/multiplayer/matches/{MATCH}", json={"gameId": GAME, "mode": "multiplayer"})
    r = client.get(f"/matches/{MATCH}", headers=auth())
    assert r.status_code == 200
    assert internal.calls[0].headers["x-user-id"] == USER


def test_not_found_codes_depend_on_origin(env):
    client, internal = env
    internal.on("GET", f"/internal/single-player/games/{GAME}", status=404, json={"detail": "x"})
    internal.on("GET", f"/internal/multiplayer/matches/{MATCH}", status=404, json={"detail": "x"})
    assert client.get(f"/games/{GAME}", headers=auth()).json()["error"]["code"] == "GAME_NOT_FOUND"
    assert client.get(f"/matches/{MATCH}", headers=auth()).json()["error"]["code"] == "MATCH_NOT_FOUND"
    internal.on("GET", f"/internal/profile/users/{USER}/profile", status=404, json={"detail": "x"})
    assert client.get("/profile/me", headers=auth()).json()["error"]["code"] == "NOT_FOUND"


def test_contract_errors_pass_through(env):
    client, internal = env
    err = {"error": {"code": "MATCH_NOT_FOUND", "message": "Texto del servicio"}}
    internal.on("GET", f"/internal/multiplayer/matches/{MATCH}", status=404, json=err)
    r = client.get(f"/matches/{MATCH}", headers=auth())
    assert r.status_code == 404 and r.json() == err


def test_malformed_ids_never_reach_internal(env):
    client, internal = env
    assert client.get("/games/../../auth", headers=auth()).status_code == 404
    r = client.get("/games/no-es-uuid", headers=auth())
    assert r.status_code == 404 and r.json()["error"]["code"] == "GAME_NOT_FOUND"
    r = client.get("/matches/no-es-uuid", headers=auth())
    assert r.status_code == 404 and r.json()["error"]["code"] == "MATCH_NOT_FOUND"
    assert internal.calls == []


def test_tutor_and_account_deletion_not_exposed(env):
    client, _ = env
    assert client.get("/tutor/analyses", headers=auth()).status_code == 404
    assert client.delete("/auth/account", headers=auth()).status_code in (404, 405)


# ---------------------------------------------------------------------- home

PROFILE = {"userId": USER, "username": "ana", "createdAt": "2026-10-10T15:00:00Z"}
STATS = {"gamesPlayed": 1, "wins": 1, "losses": 0, "draws": 0}
GAMES = {"items": [{"gameId": GAME, "mode": "local"}], "nextCursor": "c1"}


def home_routes(internal, profile=200, stats=200, games=200):
    internal.on("GET", f"/internal/profile/users/{USER}/profile", status=profile, json=PROFILE if profile == 200 else {"x": 1})
    internal.on("GET", f"/internal/profile/users/{USER}/stats", status=stats, json=STATS if stats == 200 else {"x": 1})
    internal.on("GET", "/internal/logic/games", status=games, json=GAMES if games == 200 else {"x": 1})


def test_home_all_sections(env):
    client, internal = env
    home_routes(internal)
    r = client.get("/home", headers=auth())
    assert r.status_code == 200
    assert r.json() == {
        "profile": PROFILE,
        "stats": STATS,
        "recentGames": GAMES["items"],
        "unavailable": [],
    }
    games_call = next(c for c in internal.calls if c.url.path == "/internal/logic/games")
    assert games_call.url.params["limit"] == "5" and games_call.url.params["userId"] == USER


def test_home_partial_failure_is_200_with_unavailable(env):
    client, internal = env
    home_routes(internal, stats=503)
    r = client.get("/home", headers=auth())
    assert r.status_code == 200
    body = r.json()
    assert body["stats"] is None and body["unavailable"] == ["stats"]
    assert body["profile"] == PROFILE and body["recentGames"] == GAMES["items"]


def test_home_timeout_in_one_section(env):
    client, internal = env
    home_routes(internal)
    internal.on("GET", "/internal/logic/games", exc=httpx.ReadTimeout("lento"))
    r = client.get("/home", headers=auth())
    assert r.status_code == 200 and r.json()["unavailable"] == ["recentGames"]


def test_home_all_failing_but_reachable_is_still_200(env):
    client, internal = env
    home_routes(internal, profile=503, stats=503, games=503)
    r = client.get("/home", headers=auth())
    assert r.status_code == 200
    assert r.json()["unavailable"] == ["profile", "stats", "recentGames"]


def test_home_503_when_internal_gateway_unreachable(env):
    client, internal = env
    for path in [f"/internal/profile/users/{USER}/profile", f"/internal/profile/users/{USER}/stats", "/internal/logic/games"]:
        internal.on("GET", path, exc=httpx.ConnectError("caído"))
    r = client.get("/home", headers=auth())
    assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICES_UNAVAILABLE"


def test_other_routes_503_when_unreachable(env):
    client, internal = env
    internal.on("GET", f"/internal/profile/users/{USER}/profile", exc=httpx.ConnectError("caído"))
    r = client.get("/profile/me", headers=auth())
    assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICES_UNAVAILABLE"


def test_refuses_to_start_without_jwt_secret(monkeypatch):
    monkeypatch.setattr(main, "JWT_SECRET", "")
    with pytest.raises(RuntimeError):
        with TestClient(main.app):
            pass
