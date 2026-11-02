"""API Gateway móvil (contratos v9, sección 5).

Puerta de la app Kotlin:
- Valida el JWT (solo Authorization: Bearer; no usa cookies).
- Agrega datos en GET /home (cada sección es independiente).
- Reenvía todo al gateway interno (/internal/*), nunca a un servicio directo.
- Responde 404 a cualquier ruta /internal/* que llegue desde fuera.
- No se conecta a Tutor.
"""

import asyncio
import base64
import binascii
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any, Callable

import httpx
import jwt
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("gateway.mobile")
logging.getLogger("httpx").setLevel(logging.WARNING)  # el gateway ya registra cada llamada

GATEWAY_INTERNAL_URL = os.getenv(
    "GATEWAY_INTERNAL_URL", "http://api-gateway-component:8080"
).rstrip("/")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM") or "HS256"
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))

MAX_PAGE_SIZE = 20  # contrato: limit máximo 20
HOME_RECENT_GAMES = 5  # contrato: /home trae las 5 más recientes

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _validate_config() -> None:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET es obligatoria: el gateway móvil no arranca sin ella")
    if JWT_ALGORITHM not in ("HS256", "HS384", "HS512"):
        raise RuntimeError("JWT_ALGORITHM debe ser HS256 (contrato)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_config()
    app.state.client = httpx.AsyncClient(
        base_url=GATEWAY_INTERNAL_URL,
        timeout=HTTP_TIMEOUT,
        follow_redirects=False,
    )
    logger.info("Gateway móvil listo; gateway interno en %s", GATEWAY_INTERNAL_URL)
    try:
        yield
    finally:
        await app.state.client.aclose()


app = FastAPI(title="Insightful Games - API Gateway móvil", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Errores (formato común, sección 1)
# --------------------------------------------------------------------------- #


class GatewayError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class UpstreamUnreachable(GatewayError):
    """No se pudo llegar al gateway interno (conexión rechazada, DNS, etc.)."""

    def __init__(self) -> None:
        super().__init__(503, "SERVICES_UNAVAILABLE", "No se pudo contactar con los servicios")


class UpstreamTimeout(GatewayError):
    def __init__(self) -> None:
        super().__init__(503, "SERVICES_UNAVAILABLE", "Los servicios no respondieron a tiempo")


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message}}
    )


@app.exception_handler(GatewayError)
async def gateway_error_handler(_: Request, exc: GatewayError):
    return error_response(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, _: RequestValidationError):
    logger.info("Validación fallida: %s", request.url.path)
    return error_response(400, "VALIDATION_ERROR", "Campos faltantes o con formato inválido")


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return error_response(404, "NOT_FOUND", "Ruta inexistente")
    if exc.status_code == 405:
        return error_response(405, "METHOD_NOT_ALLOWED", "Método no permitido")
    return error_response(exc.status_code, "HTTP_ERROR", "Error en la petición")


# --------------------------------------------------------------------------- #
# Seguridad de borde: bloquea /internal/* y descarta X-User-Id del cliente
# --------------------------------------------------------------------------- #


@app.middleware("http")
async def edge_guard(request: Request, call_next):
    path = request.url.path.lower()
    if path.strip("/").split("/")[0] == "internal":
        return error_response(404, "NOT_FOUND", "Ruta inexistente")

    # Ninguna cabecera de identidad del cliente se acepta ni se reenvía.
    request.scope["headers"] = [
        (k, v) for k, v in request.scope["headers"] if k.lower() != b"x-user-id"
    ]
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #


def current_user(request: Request) -> str:
    """Devuelve el userId (claim sub) del Bearer, o lanza 401 UNAUTHORIZED."""
    unauthorized = GatewayError(401, "UNAUTHORIZED", "Token ausente, inválido o vencido")

    scheme, _, token = (request.headers.get("authorization") or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise unauthorized
    try:
        claims = jwt.decode(
            token.strip(),
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        raise unauthorized

    sub = claims.get("sub")
    # sub va dentro de rutas internas: solo se acepta un UUID.
    if not isinstance(sub, str) or not UUID_RE.match(sub):
        raise unauthorized
    return sub


# --------------------------------------------------------------------------- #
# Llamadas al gateway interno
# --------------------------------------------------------------------------- #


async def call_internal(
    request: Request,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any = None,
    user_id: str | None = None,
) -> httpx.Response:
    headers = {"Accept": "application/json"}
    if user_id:
        headers["X-User-Id"] = user_id

    client: httpx.AsyncClient = request.app.state.client
    try:
        response = await asyncio.wait_for(
            client.request(method, path, params=params, json=json, headers=headers),
            timeout=HTTP_TIMEOUT,
        )
    except (asyncio.TimeoutError, httpx.TimeoutException):
        logger.error("Timeout: %s %s", method, path)
        raise UpstreamTimeout()
    except httpx.RequestError:
        logger.error("Gateway interno inalcanzable: %s %s", method, path)
        raise UpstreamUnreachable()

    logger.info("%s %s -> %s", method, path, response.status_code)
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
    not_found_code: str = "NOT_FOUND",
    conflict_code: str = "CONFLICT",
    unauthorized_code: str = "UNAUTHORIZED",
) -> Response:
    """Entrega la respuesta del servicio. Los errores sin formato se traducen
    según el servicio de origen (un 404 de Auth no es 'partida no encontrada')."""
    status = response.status_code
    if status == 204 or not response.content:
        return Response(status_code=status)

    payload = _payload(response)

    if response.is_success:
        if payload is None:
            return error_response(502, "UPSTREAM_ERROR", "Respuesta inesperada del servicio")
        return JSONResponse(status_code=status, content=payload)

    if _is_contract_error(payload):
        return JSONResponse(status_code=status, content=payload)

    table = {
        400: (400, "VALIDATION_ERROR", "Campos faltantes o con formato inválido"),
        401: (401, unauthorized_code, "No autorizado"),
        404: (404, not_found_code, "Recurso no encontrado"),
        409: (409, conflict_code, "Conflicto con el estado actual"),
        422: (422, "UNPROCESSABLE", "La solicitud no se pudo procesar"),
        503: (503, "SERVICES_UNAVAILABLE", "Un servicio dependiente no responde"),
        504: (503, "SERVICES_UNAVAILABLE", "Un servicio dependiente no respondió a tiempo"),
    }
    out_status, code, message = table.get(
        status, (502, "UPSTREAM_ERROR", "El servicio devolvió un error")
    )
    return error_response(out_status, code, message)


# --------------------------------------------------------------------------- #
# Lista de partidas: acepta el contrato v9 y la forma actual de Game Logic
# --------------------------------------------------------------------------- #
#
# Contrato v9:  GET /internal/logic/games -> { "items": [GameSummary], "nextCursor": "..." | null }
# Game Logic hoy (prototipo 1): una lista simple [GameSummary], sin paginar y sin matchId,
# endReason ni color. Mientras responda así, el gateway pagina aquí (cursor opaco = posición)
# y completa los campos que faltan con null. Cuando Game Logic migre, la respuesta pasa tal cual.


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int | None:
    """Posición codificada en el cursor, 0 si no hay cursor, None si no es un cursor válido."""
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        offset = int(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None
    return offset if offset >= 0 else None


def _normalize_summary(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return item
    out = dict(item)
    out.setdefault("matchId", None)
    out.setdefault("endReason", None)
    if "color" not in out:
        out["color"] = out.get("playerColor")  # Game Logic hoy: playerColor solo en vs_bot
    out.pop("playerColor", None)
    return out


def games_page(payload: Any, limit: int, cursor: str | None) -> dict[str, Any] | None:
    """Convierte la respuesta de Game Logic en { items, nextCursor }. None si no se entiende.
    Lanza GatewayError 400 si el cursor no es válido y la respuesta es una lista simple."""
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload  # contrato v9: ya viene paginado por Game Logic

    if isinstance(payload, list):
        offset = _decode_cursor(cursor)
        if offset is None:
            raise GatewayError(400, "VALIDATION_ERROR", "Cursor inválido")
        page = payload[offset : offset + limit]
        end = offset + limit
        return {
            "items": [_normalize_summary(i) for i in page],
            "nextCursor": _encode_cursor(end) if end < len(payload) else None,
        }
    return None


# --------------------------------------------------------------------------- #
# Modelos de entrada
# --------------------------------------------------------------------------- #


class RegisterData(BaseModel):
    username: str = Field(..., min_length=3, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)


class LoginData(BaseModel):
    username: str = Field(..., min_length=3, max_length=20)
    password: str = Field(..., min_length=1, max_length=128)


# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Auth (sin sesión) ---


@app.post("/auth/register")
async def register(data: RegisterData, request: Request):
    response = await call_internal(
        request, "POST", "/internal/auth/register", json=data.model_dump()
    )
    return relay(response, conflict_code="USERNAME_TAKEN")


@app.post("/auth/login")
async def login(data: LoginData, request: Request):
    response = await call_internal(
        request, "POST", "/internal/auth/login", json=data.model_dump()
    )
    # La app toma accessToken del cuerpo JSON. No hay cookie en móvil.
    return relay(response, unauthorized_code="INVALID_CREDENTIALS")


# --- Perfil y estadísticas ---


@app.get("/profile/me")
async def profile_me(request: Request, user_id: str = Depends(current_user)):
    response = await call_internal(
        request, "GET", f"/internal/profile/users/{user_id}/profile"
    )
    return relay(response)


@app.get("/stats/me")
async def stats_me(request: Request, user_id: str = Depends(current_user)):
    response = await call_internal(
        request, "GET", f"/internal/profile/users/{user_id}/stats"
    )
    return relay(response)


# --- Historial y detalle ---


@app.get("/games")
async def list_games(
    request: Request,
    limit: int | None = Query(default=None, ge=1),
    cursor: str | None = Query(default=None, max_length=512),
    user_id: str = Depends(current_user),
):
    params: dict[str, Any] = {
        "userId": user_id,
        "limit": min(limit, MAX_PAGE_SIZE) if limit else MAX_PAGE_SIZE,
    }
    if cursor:
        params["cursor"] = cursor
    response = await call_internal(request, "GET", "/internal/logic/games", params=params)
    if response.is_success:
        page = games_page(_payload(response), params["limit"], cursor)
        if page is None:
            return error_response(502, "UPSTREAM_ERROR", "Respuesta inesperada del servicio")
        return JSONResponse(status_code=200, content=page)
    return relay(response)


@app.get("/games/{game_id}")
async def get_game(game_id: str, request: Request, user_id: str = Depends(current_user)):
    """Detalle de partidas local y vs_bot (Single Player)."""
    if not UUID_RE.match(game_id):
        return error_response(404, "GAME_NOT_FOUND", "La partida no existe o no es visible")
    response = await call_internal(
        request,
        "GET",
        f"/internal/single-player/games/{game_id}",
        user_id=user_id,
    )
    return relay(response, not_found_code="GAME_NOT_FOUND")


@app.get("/matches/{match_id}")
async def get_match(match_id: str, request: Request, user_id: str = Depends(current_user)):
    """Detalle de partidas multiplayer (el id es el matchId, no el gameId)."""
    if not UUID_RE.match(match_id):
        return error_response(404, "MATCH_NOT_FOUND", "La partida no existe o no es visible")
    response = await call_internal(
        request,
        "GET",
        f"/internal/multiplayer/matches/{match_id}",
        user_id=user_id,
    )
    return relay(response, not_found_code="MATCH_NOT_FOUND")


# --- Inicio: agrega tres servicios, cada sección es independiente ---


def _recent_games(payload: Any) -> list[Any] | None:
    page = games_page(payload, HOME_RECENT_GAMES, None)
    return None if page is None else page["items"][:HOME_RECENT_GAMES]


async def _home_section(
    request: Request,
    name: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    extract: Callable[[Any], Any] | None = None,
) -> tuple[str, Any, str | None]:
    """Devuelve (nombre, datos, fallo). fallo: None | 'unreachable' | 'failed'."""
    try:
        response = await call_internal(request, "GET", path, params=params)
    except UpstreamUnreachable:
        return name, None, "unreachable"
    except GatewayError:  # timeout
        return name, None, "failed"

    if response.status_code != 200:
        return name, None, "failed"
    data = _payload(response)
    if extract is not None:
        try:
            data = extract(data)
        except GatewayError:
            data = None
    if data is None:
        return name, None, "failed"
    return name, data, None


@app.get("/home")
async def home(request: Request, user_id: str = Depends(current_user)):
    results = await asyncio.gather(
        _home_section(request, "profile", f"/internal/profile/users/{user_id}/profile"),
        _home_section(request, "stats", f"/internal/profile/users/{user_id}/stats"),
        _home_section(
            request,
            "recentGames",
            "/internal/logic/games",
            params={"userId": user_id, "limit": HOME_RECENT_GAMES},
            extract=_recent_games,
        ),
    )

    # 503 solo si no se puede llegar al gateway interno (fallan las tres por conexión).
    if all(failure == "unreachable" for _, _, failure in results):
        raise UpstreamUnreachable()

    body: dict[str, Any] = {name: data for name, data, _ in results}
    body["unavailable"] = [name for name, _, failure in results if failure is not None]
    return JSONResponse(status_code=200, content=body)
