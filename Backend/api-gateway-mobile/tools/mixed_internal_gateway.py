"""Gateway interno MIXTO, solo para probar el gateway móvil y la app.

Hace de gateway interno (/internal/*). Cada ruta va al servicio REAL si pones su URL, y si no, a la
simulación de fake_internal_gateway.py. Así pruebas con lo que ya sirve y simulas lo que falta.
Mientras el gateway web real no tenga passthrough (GW-04), este es el único camino de punta a punta.

Servicio real (variable de entorno)         Si no está definida
------------------------------------------  -------------------------------------------
AUTH_URL            http://localhost:8081   registro y login simulados
PROFILE_URL         http://localhost:8087   perfil y estadísticas simulados
LOGIC_URL           http://localhost:8082   lista y partidas simuladas
SINGLE_PLAYER_URL   http://localhost:8083   (ver SINGLE_PLAYER_MODE)

SINGLE_PLAYER_MODE = fake | via-logic | real
    fake       (por omisión sin LOGIC_URL) detalle simulado.
    via-logic  (por omisión con LOGIC_URL) simula SP-01/SP-05: sirve /internal/single-player/games/{id}
               leyendo la partida REAL de Game Logic y aplicando la regla de visibilidad (404 si no eres
               participante). Hoy Single Player no sirve de verdad porque llama a /logic/*, que ya no existe.
    real       reenvía a SINGLE_PLAYER_URL /games/{id} (cuando Single Player migre).
MULTIPLAYER_MODE   = fake | via-logic   (Multiplayer no existe; via-logic lee by-match de Game Logic)
LOGIC_ADAPT        = 0 (por omisión) | 1
    0  Game Logic ya entrega { items, nextCursor } (GL-04): la respuesta real pasa sin tocarla.
    1  solo para un Game Logic ANTIGUO: convierte { matches, cursor } en { items, nextCursor } y completa
       matchId, endReason y color consultando cada partida.

Uso (puerto 8080 = GATEWAY_INTERNAL_URL del gateway móvil):
    JWT_SECRET=<el mismo del gateway móvil> AUTH_URL=... uvicorn --app-dir tools mixed_internal_gateway:app --port 8080
"""

import base64
import os
import sys
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_internal_gateway as sim  # noqa: E402  (exige JWT_SECRET, igual que el simulado)

FORWARD_HEADERS = ("content-type", "x-user-id", "accept")


def err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def encode_cursor(page: int) -> str:
    return base64.urlsafe_b64encode(str(page).encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> int:
    padded = cursor + "=" * (-len(cursor) % 4)
    page = int(base64.urlsafe_b64decode(padded.encode()).decode())
    if page < 1:
        raise ValueError("página < 1")
    return page


def make_app(
    real: dict[str, httpx.AsyncClient],
    *,
    single_player_mode: str | None = None,
    multiplayer_mode: str | None = None,
    adapt: bool = True,
) -> FastAPI:
    """real: nombre de servicio ('auth', 'profile', 'logic', 'single-player') -> cliente HTTP."""
    sp_mode = single_player_mode or ("via-logic" if "logic" in real else "fake")
    mp_mode = multiplayer_mode or ("via-logic" if "logic" in real else "fake")
    if sp_mode == "real" and "single-player" not in real:
        raise ValueError("SINGLE_PLAYER_MODE=real exige SINGLE_PLAYER_URL")
    if "via-logic" in (sp_mode, mp_mode) and "logic" not in real:
        raise ValueError("via-logic exige LOGIC_URL")

    app = FastAPI(title="Gateway interno mixto (pruebas)")
    sim_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=sim.app), base_url="http://sim")

    def relay(r: httpx.Response) -> Response:
        if r.status_code == 204 or not r.content:
            return Response(status_code=r.status_code)
        return Response(
            content=r.content,
            status_code=r.status_code,
            media_type=r.headers.get("content-type", "application/json"),
        )

    async def call(client, method, path, *, params=None, content=None, headers=None):
        """Devuelve httpx.Response, o None si el servicio no responde."""
        try:
            return await client.request(method, path, params=params, content=content, headers=headers)
        except httpx.RequestError:
            return None

    unavailable = lambda: err(503, "SERVICES_UNAVAILABLE", "Un servicio dependiente no responde")  # noqa: E731

    # ----------------------------------------------------------- Game Logic (lista)

    async def enrich(item: dict, user_id: str) -> dict:
        """El resumen real de Game Logic no trae matchId, endReason ni color: se leen de la partida."""
        out = {**item, "matchId": None, "endReason": None, "color": None}
        r = await call(real["logic"], "GET", f"/internal/logic/games/{item.get('gameId')}")
        if r is not None and r.status_code == 200:
            state = r.json()
            out["matchId"] = state.get("matchId")
            out["endReason"] = state.get("endReason")
            if state.get("mode") != "local":
                out["color"] = next(
                    (p.get("color") for p in state.get("participants") or [] if p.get("userId") == user_id),
                    None,
                )
        return out

    async def logic_list(params: dict) -> Response:
        user_id = params.get("userId", "")
        try:
            page = decode_cursor(params["cursor"]) if params.get("cursor") else 1
        except (ValueError, UnicodeDecodeError):
            return err(400, "VALIDATION_ERROR", "Cursor inválido")
        upstream = {"userId": user_id, "limit": params.get("limit", 20), "cursor": page}
        r = await call(real["logic"], "GET", "/internal/logic/games", params=upstream)
        if r is None:
            return unavailable()
        if r.status_code != 200:
            return relay(r)
        data = r.json()
        if isinstance(data, dict) and "items" in data:
            return relay(r)  # Game Logic ya migró (GL-04): sin transformación
        items = [await enrich(m, user_id) for m in data.get("matches", [])]
        nxt = data.get("cursor")
        return JSONResponse({"items": items, "nextCursor": encode_cursor(nxt) if nxt else None})

    # ------------------------------------------------ detalle vía Game Logic (SP/MP)

    def is_visible(state: dict, user_id: str) -> bool:
        mine = any(p.get("userId") == user_id for p in state.get("participants") or [])
        return mine or state.get("visibility") == "shared"

    async def detail_via_logic(kind: str, key: str, user_id: str | None) -> Response:
        if not user_id:
            return err(401, "UNAUTHORIZED", "Falta X-User-Id: el gateway debe ponerlo")
        not_found = "GAME_NOT_FOUND" if kind == "game" else "MATCH_NOT_FOUND"
        path = f"/internal/logic/games/{key}" if kind == "game" else f"/internal/logic/games/by-match/{key}"
        r = await call(real["logic"], "GET", path)
        if r is None:
            return unavailable()
        if r.status_code == 404:
            return err(404, not_found, "La partida no existe o no es visible")
        if r.status_code != 200:
            return relay(r)
        state = r.json()
        if (kind == "game") == (state.get("mode") == "multiplayer"):
            # /games/{id} es solo local y vs_bot; /matches/{id} es solo multiplayer
            return err(404, not_found, "La partida no existe o no es visible")
        if not is_visible(state, user_id):
            return err(404, not_found, "La partida no existe o no es visible")
        return JSONResponse(state)

    # ------------------------------------------------------------------- enrutado

    @app.get("/health")
    async def health():
        return {"status": "ok", "real": sorted(real), "singlePlayer": sp_mode, "multiplayer": mp_mode, "adapt": adapt}

    @app.api_route("/internal/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def route(path: str, request: Request):
        parts = path.split("/")
        svc = parts[0]
        method = request.method
        params = dict(request.query_params)
        body = await request.body()
        headers = {k: v for k, v in request.headers.items() if k.lower() in FORWARD_HEADERS}
        full = f"/internal/{path}"
        user_id = request.headers.get("x-user-id")

        if svc == "logic" and "logic" in real:
            if adapt and method == "GET" and path.rstrip("/") == "logic/games":
                return await logic_list(params)
        elif svc == "single-player" and parts[1:2] == ["games"] and len(parts) == 3 and method == "GET":
            if sp_mode == "via-logic":
                return await detail_via_logic("game", parts[2], user_id)
            if sp_mode == "real":  # SP-05 pendiente: hoy expone /games/{id} sin prefijo interno
                r = await call(real["single-player"], "GET", f"/games/{parts[2]}", headers=headers)
                return unavailable() if r is None else relay(r)
        elif svc == "multiplayer" and parts[1:2] == ["matches"] and len(parts) == 3 and method == "GET":
            if mp_mode == "via-logic":
                return await detail_via_logic("match", parts[2], user_id)
        elif svc == "profile" and "profile" not in real and "auth" in real:
            # Usuarios reales (Auth real) que el simulado no conoce.
            if parts[-1] == "profile" and len(parts) == 4:
                created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                return JSONResponse({"userId": parts[2], "username": f"usuario-{parts[2][:8]}", "createdAt": created})

        client = real.get(svc)
        if client is None or (svc == "single-player" and sp_mode != "real"):
            client = sim_client
        r = await call(client, method, full, params=params, content=body or None, headers=headers)
        return unavailable() if r is None else relay(r)

    return app


def _from_env() -> FastAPI:
    timeout = float(os.getenv("HTTP_TIMEOUT", "10"))
    real = {}
    for svc, var in (("auth", "AUTH_URL"), ("profile", "PROFILE_URL"), ("logic", "LOGIC_URL"),
                     ("single-player", "SINGLE_PLAYER_URL")):
        if os.getenv(var):
            real[svc] = httpx.AsyncClient(base_url=os.environ[var].rstrip("/"), timeout=timeout)
    return make_app(
        real,
        single_player_mode=os.getenv("SINGLE_PLAYER_MODE") or None,
        multiplayer_mode=os.getenv("MULTIPLAYER_MODE") or None,
        adapt=os.getenv("LOGIC_ADAPT", "0") == "1",
    )


app = _from_env() if os.getenv("MIXED_AUTOSTART", "1") == "1" else None
