"""API Gateway web (contrato técnico definitivo, sección 7).

- Valida la sesión: cookie `session` primero, Bearer después (HS256, exige exp y sub).
- Pone X-User-Id a partir del sub; nunca usa el que envía el cliente.
- Emite y borra la cookie de sesión.
- Rutas públicas (7.4.1), passthrough /internal/* (7.4.2) y dos WebSocket
  (validan Origin y sesión, en ese orden).
"""

import asyncio
import inspect
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any

import httpx
import jwt
import websockets
from fastapi import Depends, FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("gateway.web")
logging.getLogger("httpx").setLevel(logging.WARNING)

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM") or "HS256"
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() == "true"

SESSION_COOKIE = "session"
SESSION_MAX_AGE = 3600
MAX_PAGE_SIZE = 20

# nombre en /internal/<nombre>/*  ->  URL base del servicio
UPSTREAMS: dict[str, str] = {
    name: url.rstrip("/")
    for name, url in {
        "auth": os.getenv("AUTH_URL", "http://auth-component:8081"),
        "logic": os.getenv("GAME_LOGIC_URL", "http://game-logic-component:8082"),
        "single-player": os.getenv("SINGLE_PLAYER_URL", "http://single-player-component:8083"),
        "multiplayer": os.getenv("MULTIPLAYER_URL", "http://multiplayer-component:8084"),
        "tutor": os.getenv("TUTOR_URL", "http://tutor-component:8085"),
        "engine": os.getenv("BOTCITO_URL", "http://botcito-component:8086"),
        "profile": os.getenv("PROFILE_URL", "http://profile-stats-component:8087"),
        "engine-analysis": os.getenv(
            "BOTCITO_ANALYSIS_URL", "http://botcito-analysis-component:8091"
        ),
    }.items()
}

# Código 404 según el servicio de origen (traducción de errores, 7.3)
NOT_FOUND_CODE = {
    "single-player": "GAME_NOT_FOUND",
    "logic": "GAME_NOT_FOUND",
    "multiplayer": "MATCH_NOT_FOUND",
    "tutor": "ANALYSIS_NOT_FOUND",
    "profile": "PROFILE_NOT_FOUND",
}

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
ORIGIN_RE = re.compile(r"^https?://[a-z0-9.-]+(:\d+)?$")

WS_ALLOWED_ORIGINS: frozenset[str] = frozenset()


def _validate_config() -> None:
    """El gateway no arranca con configuración insegura (7.4.4 y 7.3)."""
    global WS_ALLOWED_ORIGINS
    if len(JWT_SECRET.encode()) < 32:
        raise RuntimeError("JWT_SECRET es obligatoria y debe tener al menos 32 bytes")
    if JWT_ALGORITHM != "HS256":
        raise RuntimeError("JWT_ALGORITHM debe ser HS256")
    origins = [
        o.strip().lower()
        for o in os.getenv("WS_ALLOWED_ORIGINS", "").split(",")
        if o.strip()
    ]
    if not origins:
        raise RuntimeError("WS_ALLOWED_ORIGINS es obligatoria")
    for origin in origins:
        if not ORIGIN_RE.match(origin):
            raise RuntimeError(
                f"WS_ALLOWED_ORIGINS inválido: {origin!r} "
                "(use esquema://host[:puerto], sin barra final ni comodines)"
            )
    WS_ALLOWED_ORIGINS = frozenset(origins)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_config()
    app.state.client = httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=False)
    logger.info("Gateway web listo; orígenes WebSocket: %s", sorted(WS_ALLOWED_ORIGINS))
    try:
        yield
    finally:
        await app.state.client.aclose()


app = FastAPI(title="Insightful Games - API Gateway web", lifespan=lifespan)

# --------------------------------------------------------------------------- #
# Errores (formato común, 4.1)
# --------------------------------------------------------------------------- #


class GatewayError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class UpstreamUnreachable(GatewayError):
    def __init__(self) -> None:
        super().__init__(503, "SERVICES_UNAVAILABLE", "Servicio destino no disponible")


class UpstreamTimeout(GatewayError):
    def __init__(self) -> None:
        super().__init__(503, "SERVICES_UNAVAILABLE", "El servicio destino no respondió a tiempo")


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(GatewayError)
async def gateway_error_handler(_: Request, exc: GatewayError):
    return error_response(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, __: RequestValidationError):
    return error_response(400, "VALIDATION_ERROR", "Campos faltantes o con formato inválido")


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException):
    if exc.status_code in (404, 405):  # el catálogo no tiene 405
        return error_response(404, "NOT_FOUND", "Ruta inexistente")
    if exc.status_code == 400:
        return error_response(400, "VALIDATION_ERROR", "Campos faltantes o con formato inválido")
    if exc.status_code == 401:
        return error_response(401, "UNAUTHORIZED", "Sesión ausente, inválida o vencida")
    return error_response(500, "INTERNAL_ERROR", "Error inesperado")


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception):
    logger.exception("Error no controlado: %s", type(exc).__name__)
    return error_response(500, "INTERNAL_ERROR", "Error inesperado")


@app.middleware("http")
async def no_store(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


# --------------------------------------------------------------------------- #
# Sesión (cookie primero, luego Bearer)
# --------------------------------------------------------------------------- #


def user_from_token(token: str | None) -> str | None:
    """userId (claim sub, debe ser UUID) o None si el token no es válido."""
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) and UUID_RE.match(sub) else None


def current_user(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        scheme, _, value = (request.headers.get("authorization") or "").partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            token = value.strip()
    user_id = user_from_token(token)
    if user_id is None:
        raise GatewayError(401, "UNAUTHORIZED", "Sesión ausente, inválida o vencida")
    return user_id


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_MAX_AGE, path="/",
        httponly=True, samesite="lax", secure=COOKIE_SECURE,
    )


def _clear_session_cookie(response: Response) -> None:
    response.set_cookie(
        SESSION_COOKIE, "", max_age=0, path="/",
        httponly=True, samesite="lax", secure=COOKIE_SECURE,
    )


# --------------------------------------------------------------------------- #
# Reenvío HTTP
# --------------------------------------------------------------------------- #


async def forward(
    request: Request,
    method: str,
    service: str,
    path: str,
    *,
    user_id: str | None = None,
    params: Any = None,
    timeout: float | None = None,
) -> httpx.Response:
    """Llama a {servicio}/internal/{service}{path}. X-User-Id solo se pone si
    se pasa user_id (el sub validado o, en el passthrough, el de quien llama)."""
    url = f"{UPSTREAMS[service]}/internal/{service}{path}"
    headers = {"Accept": request.headers.get("accept") or "application/json"}

    body = None
    if method not in ("GET", "HEAD"):
        body = await request.body()
        if body:
            headers["Content-Type"] = request.headers.get("content-type") or "application/json"
    if request.headers.get("idempotency-key"):
        headers["Idempotency-Key"] = request.headers["idempotency-key"]
    if user_id:
        headers["X-User-Id"] = user_id

    try:
        response = await request.app.state.client.request(
            method, url, headers=headers, params=params, content=body,
            timeout=timeout or HTTP_TIMEOUT,
        )
    except httpx.TimeoutException:
        logger.error("Timeout: %s %s/%s", method, service, path)
        raise UpstreamTimeout()
    except httpx.RequestError:
        logger.error("Servicio inalcanzable: %s %s/%s", method, service, path)
        raise UpstreamUnreachable()

    logger.info("%s %s%s -> %s", method, service, path, response.status_code)
    return response


def _payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _is_contract_error(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("error"), dict)
        and bool(payload["error"].get("code"))
        and bool(payload["error"].get("message"))
    )


def relay(
    response: httpx.Response,
    *,
    service: str,
    conflict_code: str | None = None,
    unauthorized_code: str = "UNAUTHORIZED",
) -> Response:
    """Entrega la respuesta del servicio a un cliente. Los errores con formato
    común pasan tal cual; los que no lo tienen se traducen según el servicio."""
    extra: dict[str, str] = {}
    if response.headers.get("idempotency-replayed"):
        extra["Idempotency-Replayed"] = response.headers["idempotency-replayed"]

    status = response.status_code
    payload = _payload(response)

    if response.is_success:
        if status == 204 or not response.content:
            return Response(status_code=status, headers=extra)
        if payload is None:
            return error_response(502, "UPSTREAM_ERROR", "Respuesta inesperada del servicio")
        return JSONResponse(status_code=status, content=payload, headers=extra)

    if _is_contract_error(payload):
        return JSONResponse(status_code=status, content=payload, headers=extra)

    table: dict[int, tuple[int, str, str]] = {
        400: (400, "VALIDATION_ERROR", "Campos faltantes o con formato inválido"),
        401: (401, unauthorized_code, "No autorizado"),
        404: (404, NOT_FOUND_CODE.get(service, "NOT_FOUND"), "Recurso no encontrado"),
        503: (503, "SERVICES_UNAVAILABLE", "Un servicio dependiente no responde"),
        504: (503, "SERVICES_UNAVAILABLE", "Un servicio dependiente no respondió a tiempo"),
    }
    if conflict_code:
        table[409] = (409, conflict_code, "Conflicto con el estado actual")
    out_status, code, message = table.get(
        status, (502, "UPSTREAM_ERROR", "El servicio devolvió un error")
    )
    return error_response(out_status, code, message, ) if not extra else JSONResponse(
        status_code=out_status,
        content={"error": {"code": code, "message": message}},
        headers=extra,
    )


async def _public(
    request: Request, method: str, service: str, path: str,
    user_id: str | None = None, **kwargs: Any,
) -> Response:
    return relay(
        await forward(request, method, service, path, user_id=user_id, **kwargs),
        service=service,
    )


def _not_found(code: str) -> JSONResponse:
    return error_response(404, code, "La partida no existe o no es visible")


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #


@app.get("/health")
async def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


@app.post("/auth/register")
async def register(request: Request):
    response = await forward(request, "POST", "auth", "/register")
    return relay(response, service="auth", conflict_code="USERNAME_TAKEN")


@app.post("/auth/login")
async def login(request: Request):
    response = await forward(request, "POST", "auth", "/login")
    result = relay(response, service="auth", unauthorized_code="INVALID_CREDENTIALS")
    if response.status_code != 200:
        return result
    payload = _payload(response)
    token = payload.get("accessToken") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        return error_response(502, "UPSTREAM_ERROR", "Respuesta inesperada del servicio")
    _set_session_cookie(result, token)
    return result


@app.post("/auth/logout")
async def logout():
    response = Response(status_code=204)
    _clear_session_cookie(response)
    return response


@app.delete("/auth/account")
async def delete_account(request: Request, user_id: str = Depends(current_user)):
    # La saga puede tardar hasta 45 s: 4 × HTTP_TIMEOUT
    response = await forward(
        request, "DELETE", "auth", "/account", user_id=user_id, timeout=4 * HTTP_TIMEOUT
    )
    result = relay(response, service="auth")
    if response.status_code == 204:
        _clear_session_cookie(result)
    return result


# --------------------------------------------------------------------------- #
# Partidas local y vs_bot (Single Player) e historial (Game Logic)
# --------------------------------------------------------------------------- #


@app.post("/games")
async def create_game(request: Request, user_id: str = Depends(current_user)):
    return await _public(request, "POST", "single-player", "/games", user_id)


@app.get("/games")
async def list_games(
    request: Request,
    limit: int | None = Query(default=None, ge=1),
    cursor: str | None = Query(default=None, max_length=512),
    user_id: str = Depends(current_user),
):
    params: dict[str, Any] = {
        "userId": user_id,  # siempre el sub, nunca el del cliente
        "limit": min(limit, MAX_PAGE_SIZE) if limit else MAX_PAGE_SIZE,
    }
    if cursor:
        params["cursor"] = cursor
    return await _public(request, "GET", "logic", "/games", params=params)


@app.get("/games/{game_id}")
async def get_game(game_id: str, request: Request, user_id: str = Depends(current_user)):
    if not UUID_RE.match(game_id):
        return _not_found("GAME_NOT_FOUND")
    return await _public(request, "GET", "single-player", f"/games/{game_id}", user_id)


@app.post("/games/{game_id}/resign")
async def resign_game(game_id: str, request: Request, user_id: str = Depends(current_user)):
    if not UUID_RE.match(game_id):
        return _not_found("GAME_NOT_FOUND")
    return await _public(request, "POST", "single-player", f"/games/{game_id}/resign", user_id)


@app.patch("/games/{game_id}/visibility")
async def game_visibility(game_id: str, request: Request, user_id: str = Depends(current_user)):
    if not UUID_RE.match(game_id):
        return _not_found("GAME_NOT_FOUND")
    return await _public(request, "PATCH", "single-player", f"/games/{game_id}/visibility", user_id)


# --------------------------------------------------------------------------- #
# Multijugador
# --------------------------------------------------------------------------- #


@app.post("/matches")
async def create_match(request: Request, user_id: str = Depends(current_user)):
    return await _public(request, "POST", "multiplayer", "/matches", user_id)


@app.post("/matches/{match_id}/join")
async def join_match(match_id: str, request: Request, user_id: str = Depends(current_user)):
    if not UUID_RE.match(match_id):
        return _not_found("MATCH_NOT_FOUND")
    return await _public(request, "POST", "multiplayer", f"/matches/{match_id}/join", user_id)


@app.get("/matches/{match_id}")
async def get_match(match_id: str, request: Request, user_id: str = Depends(current_user)):
    if not UUID_RE.match(match_id):
        return _not_found("MATCH_NOT_FOUND")
    return await _public(request, "GET", "multiplayer", f"/matches/{match_id}", user_id)


@app.post("/matches/{match_id}/resign")
async def resign_match(match_id: str, request: Request, user_id: str = Depends(current_user)):
    if not UUID_RE.match(match_id):
        return _not_found("MATCH_NOT_FOUND")
    return await _public(request, "POST", "multiplayer", f"/matches/{match_id}/resign", user_id)


@app.patch("/matches/{match_id}/visibility")
async def match_visibility(match_id: str, request: Request, user_id: str = Depends(current_user)):
    if not UUID_RE.match(match_id):
        return _not_found("MATCH_NOT_FOUND")
    return await _public(request, "PATCH", "multiplayer", f"/matches/{match_id}/visibility", user_id)


# --------------------------------------------------------------------------- #
# Tutor
# --------------------------------------------------------------------------- #


@app.post("/tutor/analyses")
async def create_analysis(request: Request, user_id: str = Depends(current_user)):
    return await _public(request, "POST", "tutor", "/analyses", user_id)


@app.get("/tutor/analyses/{analysis_id}")
async def get_analysis(analysis_id: str, request: Request, user_id: str = Depends(current_user)):
    if not UUID_RE.match(analysis_id):
        return error_response(404, "ANALYSIS_NOT_FOUND", "El análisis no existe o no es visible")
    return await _public(request, "GET", "tutor", f"/analyses/{analysis_id}", user_id)


@app.get("/tutor/analyses/{analysis_id}/result")
async def get_analysis_result(
    analysis_id: str, request: Request, user_id: str = Depends(current_user)
):
    if not UUID_RE.match(analysis_id):
        return error_response(404, "ANALYSIS_NOT_FOUND", "El análisis no existe o no es visible")
    return await _public(request, "GET", "tutor", f"/analyses/{analysis_id}/result", user_id)


# --------------------------------------------------------------------------- #
# Perfil y estadísticas (la identidad sale del JWT, no del cliente)
# --------------------------------------------------------------------------- #


@app.get("/profile/me")
async def profile_me(request: Request, user_id: str = Depends(current_user)):
    return await _public(request, "GET", "profile", f"/users/{user_id}/profile")


@app.get("/stats/me")
async def stats_me(request: Request, user_id: str = Depends(current_user)):
    return await _public(request, "GET", "profile", f"/users/{user_id}/stats")


# --------------------------------------------------------------------------- #
# Passthrough interno: /internal/<servicio>/*  (7.4.2)
# --------------------------------------------------------------------------- #
# No valida JWT ni traduce errores: los servicios (Auth, Multiplayer, workers)
# dependen de los códigos originales. Conserva método, cuerpo, query y X-User-Id.
# Solo es seguro si el puerto 8080 no se publica y Vike responde 404 a /api/internal/*.


@app.api_route("/internal/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def internal_passthrough(service: str, path: str, request: Request):
    if service not in UPSTREAMS or ".." in path.split("/"):
        return error_response(404, "NOT_FOUND", "Ruta inexistente")
    response = await forward(
        request,
        request.method,
        service,
        "/" + path,
        user_id=request.headers.get("x-user-id"),
        params=list(request.query_params.multi_items()),
    )
    extra = {}
    if response.headers.get("idempotency-replayed"):
        extra["Idempotency-Replayed"] = response.headers["idempotency-replayed"]
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type"),
        headers=extra,
    )


# --------------------------------------------------------------------------- #
# TEMPORAL (tarea GW-13): Single Player aún llama a /engine/best-move por el
# gateway. Borrar este bloque cuando use /internal/engine/best-move (SP-07, BOT-01).
# --------------------------------------------------------------------------- #


@app.api_route("/engine/{path:path}", methods=["GET", "POST"])
async def legacy_engine(path: str, request: Request):
    body = await request.body()
    try:
        r = await request.app.state.client.request(
            request.method,
            f"{UPSTREAMS['engine']}/engine/{path}",
            content=body or None,
            headers={"Content-Type": "application/json"} if body else None,
        )
    except httpx.RequestError:
        raise UpstreamUnreachable()
    return Response(content=r.content, status_code=r.status_code, media_type="application/json")


# --------------------------------------------------------------------------- #
# WebSocket: aceptar -> Origin -> sesión -> id -> servicio
# --------------------------------------------------------------------------- #

_WS_HEADERS_KW = (
    "additional_headers"
    if "additional_headers" in inspect.signature(websockets.connect).parameters
    else "extra_headers"
)


def _ws_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://"):]
    return f"{base}{path}"


async def _safe_close(ws: WebSocket, code: int, reason: str = "") -> None:
    try:
        await ws.close(code=code, reason=reason[:100])
    except Exception:  # noqa: BLE001  (el cliente ya se fue)
        pass


def _close_code_for_client(code: int | None) -> int:
    if code is None or code == 1005:
        return 1000
    if code in (1000, 1001, 1011) or 3000 <= code <= 4999:
        return code  # conserva 4401/4404 de Single Player y Multiplayer
    return 1011


async def _proxy_websocket(
    client_ws: WebSocket, service: str, resource_id: str, resource: str
) -> None:
    # Se acepta primero: un rechazo antes del accept llegaría al navegador como 1006
    await client_ws.accept()

    origin = (client_ws.headers.get("origin") or "").strip().lower()
    if not origin or origin == "null" or origin not in WS_ALLOWED_ORIGINS:
        logger.warning("WebSocket rechazado: Origin no permitido")
        await _safe_close(client_ws, 4403, "Origin no permitido")
        return

    user_id = user_from_token(client_ws.cookies.get(SESSION_COOKIE))
    if user_id is None:
        await _safe_close(client_ws, 4401, "Sesión inválida o vencida")
        return

    if not UUID_RE.match(resource_id):
        await _safe_close(client_ws, 4404, "Partida inexistente o ajena")
        return

    upstream_url = _ws_url(
        UPSTREAMS[service], f"/internal/{service}/ws/{resource}/{resource_id}"
    )
    logger.info("WebSocket %s/%s", service, resource_id)

    try:
        async with websockets.connect(
            upstream_url,
            open_timeout=8,
            close_timeout=3,
            max_size=2**20,
            **{_WS_HEADERS_KW: {"X-User-Id": user_id}},
        ) as upstream:

            async def client_to_upstream():
                while True:
                    await upstream.send(await client_ws.receive_text())

            async def upstream_to_client():
                async for message in upstream:
                    if isinstance(message, str):
                        await client_ws.send_text(message)
                    else:
                        await client_ws.send_bytes(message)

            tasks = [
                asyncio.create_task(client_to_upstream()),
                asyncio.create_task(upstream_to_client()),
            ]
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

            upstream_code = getattr(upstream, "close_code", None)
            upstream_reason = getattr(upstream, "close_reason", "") or ""

        await _safe_close(client_ws, _close_code_for_client(upstream_code), upstream_reason)

    except WebSocketDisconnect:
        logger.info("Cliente desconectado de %s/%s", service, resource_id)

    except Exception as exc:  # noqa: BLE001
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
        logger.warning("Error en WebSocket %s: %s", service, type(exc).__name__)
        if status in (401, 403):
            await _safe_close(client_ws, 4401, "Sesión inválida o vencida")
        elif status == 404:
            await _safe_close(client_ws, 4404, "Partida inexistente o ajena")
        else:
            await _safe_close(client_ws, 1011, "Servicio no disponible")


@app.websocket("/ws/games/{game_id}")
async def ws_games(websocket: WebSocket, game_id: str):
    await _proxy_websocket(websocket, "single-player", game_id, "games")


@app.websocket("/ws/matches/{match_id}")
async def ws_matches(websocket: WebSocket, match_id: str):
    await _proxy_websocket(websocket, "multiplayer", match_id, "matches")