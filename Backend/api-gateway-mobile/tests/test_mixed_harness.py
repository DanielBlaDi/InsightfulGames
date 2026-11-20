"""Cadena completa SIN red: gateway móvil -> gateway interno mixto -> servicios "reales".

Los servicios reales se imitan con httpx.MockTransport usando las respuestas que HOY dan Auth,
Profile/Stats y Game Logic (formas leídas del código). Sirve para fijar qué pasa con cada servicio
real, incluida la lista { matches, cursor } de Game Logic que todavía no cumple el contrato (GL-04).
"""

import json
import os
import sys
import time

os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["GATEWAY_INTERNAL_URL"] = "http://internal.test"
os.environ["HTTP_TIMEOUT"] = "2"
os.environ["MIXED_AUTOSTART"] = "0"

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

import main
import mixed_internal_gateway as mixed

USER = "11111111-1111-4111-8111-111111111111"
OTHER = "99999999-9999-4999-8999-999999999999"
G1, G2, G3 = (f"0000000{i}-0000-4000-8000-000000000000" for i in (1, 2, 3))
M1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def bearer(sub=USER):
    t = jwt.encode({"sub": sub, "username": "ana", "exp": int(time.time()) + 3600}, main.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {t}"}


def state(game_id, mode="local", participants=None, visibility="private", match_id=None, **kw):
    """GameState como lo devuelve hoy Game Logic (moves sin color)."""
    return {
        "gameId": game_id, "mode": mode, "visibility": visibility, "matchId": match_id,
        "participants": participants if participants is not None else [{"userId": USER, "color": "white"}],
        "botLevel": None, "timeControl": None, "clocks": None, "status": "finished", "turn": "white",
        "fen": "x", "initialFen": "x", "legalMoves": {}, "moves": [{"ply": 1, "san": "e4", "uci": "e2e4", "fenAfter": "x", "timestamp": "t"}],
        "drawOffer": None, "version": 1, "result": "white", "endReason": "checkmate",
        "createdAt": "2026-11-01T10:00:00Z", "finishedAt": "2026-11-01T10:05:00Z", **kw,
    }


class FakeService:
    """Servicio 'real' imitado: registra las llamadas y responde según un mapa (método, ruta)."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.routes: dict = {}

    def on(self, method, path, status=200, body=None, exc=None):
        self.routes[(method, path)] = (status, body, exc)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        entry = self.routes.get((request.method, request.url.path))
        if entry is None:
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "no simulada"}})
        status, body, exc = entry
        if exc:
            raise exc
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status)

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle), base_url="http://svc")


def run_chain(real, **kw):
    harness = mixed.make_app({k: v.client() for k, v in real.items()}, **kw)
    with TestClient(main.app) as client:
        main.app.state.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=harness), base_url=main.GATEWAY_INTERNAL_URL
        )
        yield client


@pytest.fixture()
def logic():
    return FakeService()


@pytest.fixture()
def chain(logic):
    yield from run_chain({"logic": logic})


# ------------------------------------------------ lista: Game Logic real { matches, cursor }


def summary(game_id, mode="local"):
    return {"gameId": game_id, "mode": mode, "status": "finished", "result": "white", "createdAt": "2026-11-01T10:00:00Z"}


def test_real_list_is_adapted_to_gamespage_and_enriched(chain, logic):
    logic.on("GET", "/internal/logic/games", body={"matches": [summary(G1, "local"), summary(G2, "multiplayer")], "cursor": 2})
    logic.on("GET", f"/internal/logic/games/{G1}", body=state(G1, "local", [{"userId": USER, "color": "white"}] * 2))
    logic.on("GET", f"/internal/logic/games/{G2}", body=state(G2, "multiplayer", [{"userId": OTHER, "color": "white"}, {"userId": USER, "color": "black"}], match_id=M1, endReason="timeout"))

    r = chain.get("/games", headers=bearer())
    assert r.status_code == 200, r.text
    body = r.json()
    local, mp = body["items"]
    assert local["matchId"] is None and local["color"] is None and local["endReason"] == "checkmate"
    assert mp["matchId"] == M1 and mp["color"] == "black" and mp["endReason"] == "timeout"
    assert body["nextCursor"]

    # la primera página pide cursor=1 (Game Logic lo exige y es 1-based)
    first = logic.calls[0]
    assert dict(first.url.params) == {"userId": USER, "limit": "20", "cursor": "1"}


def test_second_page_sends_the_page_number_to_game_logic(chain, logic):
    logic.on("GET", "/internal/logic/games", body={"matches": [summary(G1)], "cursor": 3})
    logic.on("GET", f"/internal/logic/games/{G1}", body=state(G1))
    cursor = mixed.encode_cursor(2)
    r = chain.get(f"/games?limit=5&cursor={cursor}", headers=bearer())
    assert r.status_code == 200
    assert dict(logic.calls[0].url.params) == {"userId": USER, "limit": "5", "cursor": "2"}
    assert mixed.decode_cursor(r.json()["nextCursor"]) == 3


def test_last_page_has_null_next_cursor(chain, logic):
    logic.on("GET", "/internal/logic/games", body={"matches": [], "cursor": None})
    r = chain.get("/games", headers=bearer())
    assert r.status_code == 200 and r.json() == {"items": [], "nextCursor": None}


def test_invalid_cursor_is_400(chain):
    r = chain.get("/games?cursor=basura!!", headers=bearer())
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_without_adapter_the_real_format_fails_today():
    """LOGIC_ADAPT=0 reproduce lo que pasa hoy con Game Logic sin GL-04: el gateway móvil no la entiende."""
    logic = FakeService()
    logic.on("GET", "/internal/logic/games", body={"matches": [summary(G1)], "cursor": None})
    for client in run_chain({"logic": logic}, adapt=False):
        r = client.get("/games", headers=bearer())
        assert r.status_code == 502 and r.json()["error"]["code"] == "UPSTREAM_ERROR"
        assert "cursor" not in dict(logic.calls[0].url.params)  # y Game Logic real respondería 400


def test_gamespage_from_game_logic_passes_untouched(chain, logic):
    page = {"items": [{"gameId": G1, "mode": "local", "matchId": None, "status": "finished", "result": "white",
                       "endReason": "checkmate", "color": None, "createdAt": "2026-11-01T10:00:00Z"}], "nextCursor": None}
    logic.on("GET", "/internal/logic/games", body=page)
    assert chain.get("/games", headers=bearer()).json() == page
    assert len(logic.calls) == 1  # sin llamadas extra de enriquecimiento


# ------------------------------------------------------------ detalle vía Game Logic real


def test_game_detail_visible_only_to_participants(chain, logic):
    logic.on("GET", f"/internal/logic/games/{G1}", body=state(G1))
    assert chain.get(f"/games/{G1}", headers=bearer()).json()["gameId"] == G1
    r = chain.get(f"/games/{G1}", headers=bearer(OTHER))
    assert r.status_code == 404 and r.json()["error"]["code"] == "GAME_NOT_FOUND"


def test_game_detail_unknown_game_is_game_not_found(chain, logic):
    logic.on("GET", f"/internal/logic/games/{G3}", status=404, body={"error": {"code": "GAME_NOT_FOUND", "message": "x"}})
    r = chain.get(f"/games/{G3}", headers=bearer())
    assert r.status_code == 404 and r.json()["error"]["code"] == "GAME_NOT_FOUND"


def test_multiplayer_game_is_not_served_by_games_route(chain, logic):
    logic.on("GET", f"/internal/logic/games/{G2}", body=state(G2, "multiplayer", match_id=M1))
    r = chain.get(f"/games/{G2}", headers=bearer())
    assert r.status_code == 404


def test_match_detail_by_match_id_and_shared_visibility(chain, logic):
    logic.on("GET", f"/internal/logic/games/by-match/{M1}", body=state(G2, "multiplayer", match_id=M1))
    assert chain.get(f"/matches/{M1}", headers=bearer()).status_code == 200
    denied = chain.get(f"/matches/{M1}", headers=bearer(OTHER))
    assert denied.status_code == 404 and denied.json()["error"]["code"] == "MATCH_NOT_FOUND"

    logic.on("GET", f"/internal/logic/games/by-match/{M1}", body=state(G2, "multiplayer", visibility="shared", match_id=M1))
    assert chain.get(f"/matches/{M1}", headers=bearer(OTHER)).status_code == 200


def test_client_x_user_id_never_reaches_game_logic_detail(chain, logic):
    logic.on("GET", f"/internal/logic/games/{G1}", body=state(G1))
    r = chain.get(f"/games/{G1}", headers={**bearer(OTHER), "X-User-Id": USER})
    assert r.status_code == 404  # manda el sub del token, no la cabecera del cliente


# ------------------------------------------------------------------- fallos y degradación


def test_game_logic_down_gives_503_and_home_degrades(chain, logic):
    logic.on("GET", "/internal/logic/games", exc=httpx.ConnectError("caído"))
    r = chain.get("/games", headers=bearer())
    assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICES_UNAVAILABLE"

    home = chain.get("/home", headers=bearer())
    assert home.status_code == 200
    assert "recentGames" in home.json()["unavailable"] and home.json()["recentGames"] is None
    assert home.json()["stats"] is not None  # las estadísticas simuladas siguen disponibles


def test_home_with_real_profile_not_found_marks_profile_unavailable():
    profile = FakeService()
    profile.on("GET", f"/internal/profile/users/{USER}/profile", status=404, body={"error": {"code": "PROFILE_NOT_FOUND", "message": "x"}})
    profile.on("GET", f"/internal/profile/users/{USER}/stats", body={"gamesPlayed": 0, "wins": 0, "losses": 0, "draws": 0})
    for client in run_chain({"profile": profile}):
        home = client.get("/home", headers=bearer()).json()
        assert home["profile"] is None and "profile" in home["unavailable"]
        assert home["stats"] == {"gamesPlayed": 0, "wins": 0, "losses": 0, "draws": 0}
        r = client.get("/profile/me", headers=bearer())
        assert r.status_code == 404 and r.json()["error"]["code"] == "PROFILE_NOT_FOUND"


# ------------------------------------------------- Auth real y servicios simulados


def test_real_auth_with_simulated_profile_and_games():
    auth = FakeService()
    token = bearer()["Authorization"].split()[1]
    auth.on("POST", "/internal/auth/login", body={"accessToken": token, "expiresIn": 3600, "user": {"userId": USER, "username": "ana"}})
    auth.on("POST", "/internal/auth/register", status=409, body={"error": {"code": "USERNAME_TAKEN", "message": "x"}})
    for client in run_chain({"auth": auth}):
        login = client.post("/auth/login", json={"username": "ana", "password": "12345678"})
        assert login.status_code == 200 and login.json()["accessToken"] == token
        assert client.post("/auth/register", json={"username": "ana", "password": "12345678"}).json()["error"]["code"] == "USERNAME_TAKEN"

        profile = client.get("/profile/me", headers=bearer()).json()  # el simulado no conoce a este usuario real
        assert profile["userId"] == USER and profile["username"].startswith("usuario-")
        page = client.get("/games?limit=5", headers=bearer()).json()
        assert len(page["items"]) == 5 and page["nextCursor"]


def test_simulated_multiplayer_match_detail():
    from fake_internal_gateway import games_for

    match_id = next(g["matchId"] for g in games_for(USER) if g["matchId"])
    for client in run_chain({}):
        r = client.get(f"/matches/{match_id}", headers=bearer())
        assert r.status_code == 200 and r.json()["matchId"] == match_id


# ------------------------------------------------------------------- configuración


def test_via_logic_requires_logic_url():
    with pytest.raises(ValueError):
        mixed.make_app({}, single_player_mode="via-logic")
    with pytest.raises(ValueError):
        mixed.make_app({}, single_player_mode="real")


def test_cursor_roundtrip():
    assert mixed.decode_cursor(mixed.encode_cursor(7)) == 7
    with pytest.raises(ValueError):
        mixed.decode_cursor(mixed.encode_cursor(0))


def test_health_reports_what_is_real(logic):
    for client in run_chain({"logic": logic}):
        pass
    harness = mixed.make_app({"logic": logic.client()})
    body = TestClient(harness).get("/health").json()
    assert body["real"] == ["logic"] and body["singlePlayer"] == "via-logic" and body["adapt"] is True
