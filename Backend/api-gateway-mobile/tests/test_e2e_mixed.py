"""Prueba de punta a punta contra procesos REALES. Se omite sola si no defines MOBILE_GATEWAY_URL.

    MOBILE_GATEWAY_URL=http://localhost:8090 pytest tests/test_e2e_mixed.py -v

Recorre lo mismo que la app: registro, login, perfil, estadísticas, inicio, historial paginado y detalle.
Qué es real y qué es simulado lo decide el gateway interno mixto (tools/mixed_internal_gateway.py).

Si defines LOGIC_URL (Game Logic real, p. ej. http://localhost:8082) la prueba crea partidas de ese usuario
directamente en Game Logic, porque un usuario recién registrado no tiene historial.
Con PROFILE_URL real el perfil lo crea RabbitMQ al registrarse: la prueba espera hasta E2E_PROFILE_WAIT s.
"""

import os
import time
import uuid

import httpx
import jwt
import pytest

BASE = os.getenv("MOBILE_GATEWAY_URL")
LOGIC_URL = os.getenv("LOGIC_URL")
PROFILE_REAL = bool(os.getenv("PROFILE_URL"))
PROFILE_WAIT = float(os.getenv("E2E_PROFILE_WAIT", "20"))

pytestmark = pytest.mark.skipif(not BASE, reason="define MOBILE_GATEWAY_URL para correr la prueba de punta a punta")

PASSWORD = "clave-segura-123"


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=BASE, timeout=15) as client:
        yield client


@pytest.fixture(scope="module")
def session(api):
    username = "e2e" + uuid.uuid4().hex[:10]
    reg = api.post("/auth/register", json={"username": username, "password": PASSWORD})
    assert reg.status_code == 201, reg.text
    login = api.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["expiresIn"] == 3600 and body["accessToken"]
    assert "set-cookie" not in login.headers  # en móvil no hay cookie
    user_id = jwt.decode(body["accessToken"], options={"verify_signature": False})["sub"]
    return {"username": username, "userId": user_id, "headers": {"Authorization": f"Bearer {body['accessToken']}"}}


@pytest.fixture(scope="module")
def seeded(session):
    """Crea 2 partidas en Game Logic real (local y vs_bot) para el usuario. Sin LOGIC_URL no hace nada."""
    if not LOGIC_URL:
        return 0
    uid = session["userId"]
    bodies = [
        {"mode": "local", "visibility": "private", "participants": [{"userId": uid, "color": "white"}, {"userId": uid, "color": "black"}]},
        {"mode": "vs_bot", "visibility": "private", "botLevel": 5, "participants": [{"userId": uid, "color": "white"}]},
    ]
    for b in bodies:
        r = httpx.post(f"{LOGIC_URL}/internal/logic/games", json=b, timeout=15)
        assert r.status_code in (200, 201), r.text
    return len(bodies)


def test_health(api):
    assert api.get("/health").json() == {"status": "ok"}


def test_security(api, session):
    assert api.get("/home").status_code == 401
    assert api.get("/internal/auth/login").status_code == 404
    spoof = {**session["headers"], "X-User-Id": "00000000-0000-4000-8000-000000000000"}
    assert api.get("/profile/me", headers=spoof).status_code in (200, 404)  # nunca toma la cabecera del cliente


def test_profile(api, session):
    deadline = time.time() + (PROFILE_WAIT if PROFILE_REAL else 0)
    while True:
        r = api.get("/profile/me", headers=session["headers"])
        if r.status_code == 200 or time.time() >= deadline:
            break
        time.sleep(1)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body["userId"] == session["userId"] and body["username"] and body["createdAt"]


def test_stats(api, session):
    r = api.get("/stats/me", headers=session["headers"])
    assert r.status_code == 200, r.text
    assert set(r.json()) >= {"gamesPlayed", "wins", "losses", "draws"}


def test_home(api, session, seeded):
    r = api.get("/home", headers=session["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"profile", "stats", "recentGames", "unavailable"}
    assert "recentGames" not in body["unavailable"], f"recentGames no disponible: {body}"
    assert len(body["recentGames"]) <= 5


def test_history_pagination_and_detail(api, session, seeded):
    first = api.get("/games", params={"limit": 2}, headers=session["headers"])
    assert first.status_code == 200, first.text
    page = first.json()
    assert set(page) == {"items", "nextCursor"} and 0 < len(page["items"]) <= 2
    for item in page["items"]:
        assert set(item) >= {"gameId", "mode", "matchId", "status", "result", "endReason", "color", "createdAt"}

    items = list(page["items"])
    seen = {i["gameId"] for i in items}
    pages = 1
    while page["nextCursor"] and pages < 30:
        page = api.get("/games", params={"limit": 20, "cursor": page["nextCursor"]}, headers=session["headers"]).json()
        ids = {i["gameId"] for i in page["items"]}
        assert not (ids & seen), "la paginación repite partidas"
        seen |= ids
        items += page["items"]
        pages += 1
    assert len(seen) >= seeded

    single = next((i for i in items if i["mode"] in ("local", "vs_bot")), None)
    if single is None:
        pytest.skip("el usuario no tiene partidas local ni vs_bot")
    detail = api.get(f"/games/{single['gameId']}", headers=session["headers"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["gameId"] == single["gameId"]

    multi = next((i for i in items if i["mode"] == "multiplayer" and i["matchId"]), None)
    if multi:  # Multiplayer no existe: lo sirve la simulación, no el backend real
        r = api.get(f"/matches/{multi['matchId']}", headers=session["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["matchId"] == multi["matchId"]


def test_detail_hidden_from_other_users(api, session, seeded):
    first = api.get("/games", params={"limit": 1}, headers=session["headers"]).json()["items"]
    if not first:
        pytest.skip("el usuario no tiene partidas")
    other = "ot" + uuid.uuid4().hex[:10]
    api.post("/auth/register", json={"username": other, "password": PASSWORD})
    token = api.post("/auth/login", json={"username": other, "password": PASSWORD}).json()["accessToken"]
    r = api.get(f"/games/{first[0]['gameId']}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "GAME_NOT_FOUND"


def test_non_uuid_ids_are_404_without_reaching_services(api, session):
    assert api.get("/games/no-es-uuid", headers=session["headers"]).status_code == 404
    assert api.get("/matches/no-es-uuid", headers=session["headers"]).status_code == 404
