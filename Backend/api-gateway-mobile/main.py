"""API Gateway móvil (contrato técnico definitivo, secciones 4.11 y 5).

Puerta de la app Kotlin:
- Valida el JWT (solo Authorization: Bearer; no usa cookies).
- Orquesta: llama directamente a Auth, Profile/Stats y Game Logic (no depende del gateway web).
- Agrega datos en GET /home (cada sección es independiente).
- Aplica aquí la regla de visibilidad del detalle de partidas (participante o shared).
- Responde 404 a cualquier ruta /internal/* que llegue desde fuera.
- Orquesta la saga de borrado de cuenta (DELETE /auth/account); es lo único que hace con el Tutor,
  no expone ninguna de sus rutas.
"""

import asyncio
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

# nombre del servicio (el de /internal/<nombre>/*)  ->  URL base, llamada directamente
UPSTREAMS: dict[str, str] = {
    name: url.rstrip("/")
    for name, url in {
        "auth": os.getenv("AUTH_URL", "http://auth-component:8081"),
        "logic": os.getenv("GAME_LOGIC_URL", "http://game-logic-component:8082"),
        "profile": os.getenv("PROFILE_URL", "http://profile-stats-component:8087"),
        # solo para el borrado de cuenta: el móvil no expone rutas del Tutor
        "tutor": os.getenv("TUTOR_URL", "http://tutor-component:8085"),
    }.items()
}
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM") or "HS256"
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))

MIN_SECRET_BYTES = 32  # contrato 8.5: JWT_SECRET obligatoria, mínimo 32 bytes
MAX_PAGE_SIZE = 20  # contrato: limit máximo 20
HOME_RECENT_GAMES = 5  # contrato: /home trae las 5 más recientes

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _validate_config() -> None:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET es obligatoria: el gateway móvil no arranca sin ella")
    if len(JWT_SECRET.encode("utf-8")) < MIN_SECRET_BYTES:
        raise RuntimeError(
            f"JWT_SECRET debe tener al menos {MIN_SECRET_BYTES} bytes (contrato, sección 8.5)"
        )
    if JWT_ALGORITHM != "HS256":
        raise RuntimeError("JWT_ALGORITHM debe ser HS256 (contrato, sección 5)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_config()
    app.state.client = httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=False)
    logger.info("Gateway móvil listo; servicios: %s", UPSTREAMS)
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
    """No se pudo llegar al servicio (conexión rechazada, DNS, etc.)."""

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
    # El catálogo 4.12 no tiene 405: una ruta con método no soportado es una ruta inexistente.
    if exc.status_code in (404, 405):
        return error_response(404, "NOT_FOUND", "Ruta inexistente")
    if exc.status_code == 400:
        return error_response(400, "VALIDATION_ERROR", "Campos faltantes o con formato inválido")
    if exc.status_code == 401:
        return error_response(401, "UNAUTHORIZED", "Token ausente, inválido o vencido")
    return error_response(500, "INTERNAL_ERROR", "Error inesperado")


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
            algorithms=["HS256"],  # el contrato fija solo HS256
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
# Llamadas directas a los servicios
# --------------------------------------------------------------------------- #


async def call_service(
    request: Request,
    method: str,
    service: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any = None,
    user_id: str | None = None,
) -> httpx.Response:
    """Llama a {servicio}/internal/{service}{path}. X-User-Id solo se envía si se pasa user_id."""
    url = f"{UPSTREAMS[service]}/internal/{service}{path}"
    headers = {"Accept": "application/json"}
    if user_id:
        headers["X-User-Id"] = user_id

    client: httpx.AsyncClient = request.app.state.client
    try:
        response = await asyncio.wait_for(
            client.request(method, url, params=params, json=json, headers=headers),
            timeout=HTTP_TIMEOUT,
        )
    except (asyncio.TimeoutError, httpx.TimeoutException):
        logger.error("Timeout: %s %s%s", method, service, path)
        raise UpstreamTimeout()
    except httpx.RequestError:
        logger.error("Servicio inalcanzable: %s %s%s", method, service, path)
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
    not_found_code: str = "NOT_FOUND",
    conflict_code: str | None = None,
    unauthorized_code: str = "UNAUTHORIZED",
) -> Response:
    """Entrega la respuesta del servicio. Los errores sin formato se traducen
    según el servicio de origen (un 404 de Auth no es 'partida no encontrada').

    Solo se emiten códigos del catálogo 4.12. Un 409 o 422 sin formato de error no
    tiene código propio en el catálogo, así que se informa como UPSTREAM_ERROR (502),
    salvo el 409 de registro, que es USERNAME_TAKEN."""
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
        **({409: (409, conflict_code, "Conflicto con el estado actual")} if conflict_code else {}),
        503: (503, "SERVICES_UNAVAILABLE", "Un servicio dependiente no responde"),
        504: (503, "SERVICES_UNAVAILABLE", "Un servicio dependiente no respondió a tiempo"),
    }
    out_status, code, message = table.get(
        status, (502, "UPSTREAM_ERROR", "El servicio devolvió un error")
    )
    return error_response(out_status, code, message)


# --------------------------------------------------------------------------- #
# Lista de partidas: contrato 4.1 (GamesPage)
# --------------------------------------------------------------------------- #
#
# GET /internal/logic/games -> { "items": [GameSummary], "nextCursor": "..." | null }
# Game Logic ya entrega ese formato (GL-04): el gateway lo deja pasar sin transformarlo.
# Cualquier otra forma se considera una respuesta inesperada del servicio.


def games_page(payload: Any) -> dict[str, Any] | None:
    """Devuelve la página tal como la entregó Game Logic, o None si no tiene la forma { items, nextCursor }."""
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload
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
    response = await call_service(
        request, "POST", "auth", "/register", json=data.model_dump()
    )
    return relay(response, conflict_code="USERNAME_TAKEN")


@app.post("/auth/login")
async def login(data: LoginData, request: Request):
    response = await call_service(
        request, "POST", "auth", "/login", json=data.model_dump()
    )
    # La app toma accessToken del cuerpo JSON. No hay cookie en móvil.
    return relay(response, unauthorized_code="INVALID_CREDENTIALS")


# --- Borrado de cuenta (saga orquestada aquí; Auth ya no llama a nadie) ---
#
# Orden obligatorio (contrato, sección 7), cada borrado debe dar 204:
#   1. Auth GET /users/{id} (404 = ya no existe: 204)  2. Logic DELETE users/{id}
#   3. Tutor: game-ids -> Game Logic (visibilidad de cada partida) -> POST erase  4. Profile DELETE users/{id}
#   5. Auth DELETE /account (solo la fila). Sin compensación: los borrados son idempotentes y el usuario reintenta.

ERASE_CONCURRENCY = 8  # consultas simultáneas a Game Logic al resolver la visibilidad de las partidas


def _delete_unavailable(name: str) -> GatewayError:
    return GatewayError(
        503,
        "SERVICES_UNAVAILABLE",
        f"No se pudo borrar la cuenta: {name} no respondió. Intenta de nuevo",
    )


async def _delete_step(
    request: Request, name: str, method: str, service: str, path: str, user_id: str | None = None
) -> httpx.Response:
    try:
        return await call_service(request, method, service, path, user_id=user_id)
    except GatewayError:  # red o tiempo
        raise _delete_unavailable(name)


async def _erase_tutor_analyses(request: Request, user_id: str) -> None:
    """Paso del Tutor: se resuelve la visibilidad ACTUAL de cada partida en Game Logic y solo después
    se muta. Solo las partidas shared se conservan; inexistente (404), privada o cualquier valor
    inesperado se borra (fail-closed). Si Game Logic o el Tutor fallan antes del erase, no se toca nada."""
    listing = await _delete_step(request, "Tutor", "GET", "tutor", f"/users/{user_id}/game-ids")
    payload = _payload(listing) if listing.status_code == 200 else None
    game_ids = payload.get("gameIds") if isinstance(payload, dict) else None
    if not isinstance(game_ids, list) or not all(isinstance(g, str) for g in game_ids):
        logger.warning("Borrado de cuenta: el Tutor respondió %s al listar partidas", listing.status_code)
        raise _delete_unavailable("Tutor")

    gate = asyncio.Semaphore(ERASE_CONCURRENCY)

    async def keep(game_id: str) -> bool:
        async with gate:
            try:
                response = await call_service(request, "GET", "logic", f"/games/{game_id}")
            except GatewayError:
                raise _delete_unavailable("Game Logic")
        if response.status_code == 404:
            return False  # partida inexistente: se borran sus análisis
        state = _payload(response) if response.status_code == 200 else None
        if not isinstance(state, dict):
            raise _delete_unavailable("Game Logic")
        return state.get("visibility") == "shared"

    decisions = await asyncio.gather(*(keep(g) for g in game_ids))
    keep_ids = [g for g, kept in zip(game_ids, decisions) if kept]

    try:
        erased = await call_service(
            request, "POST", "tutor", f"/users/{user_id}/erase", json={"keepGameIds": keep_ids}
        )
    except GatewayError:
        raise _delete_unavailable("Tutor")
    if erased.status_code != 204:
        logger.warning("Borrado de cuenta: el Tutor respondió %s al borrar", erased.status_code)
        raise _delete_unavailable("Tutor")


async def _delete_account_saga(request: Request, user_id: str) -> None:
    exists = await _delete_step(request, "Auth", "GET", "auth", f"/users/{user_id}")
    if exists.status_code == 404:
        return  # ya estaba borrada
    if exists.status_code != 200:
        raise _delete_unavailable("Auth")

    async def delete_user_in(name: str, service: str) -> None:
        response = await _delete_step(request, name, "DELETE", service, f"/users/{user_id}")
        if response.status_code != 204:
            logger.warning("Borrado de cuenta: %s respondió %s; se corta la cadena", name, response.status_code)
            raise _delete_unavailable(name)

    await delete_user_in("Game Logic", "logic")
    await _erase_tutor_analyses(request, user_id)
    await delete_user_in("Profile/Stats", "profile")

    final = await _delete_step(request, "Auth", "DELETE", "auth", "/account", user_id=user_id)
    if final.status_code != 204:
        raise _delete_unavailable("Auth")


@app.delete("/auth/account")
async def delete_account(request: Request, user_id: str = Depends(current_user)):
    try:
        await asyncio.wait_for(_delete_account_saga(request, user_id), timeout=4 * HTTP_TIMEOUT)
    except asyncio.TimeoutError:
        raise _delete_unavailable("un servicio")
    return Response(status_code=204)


# --- Perfil y estadísticas ---


@app.get("/profile/me")
async def profile_me(request: Request, user_id: str = Depends(current_user)):
    response = await call_service(request, "GET", "profile", f"/users/{user_id}/profile")
    return relay(response)


@app.get("/stats/me")
async def stats_me(request: Request, user_id: str = Depends(current_user)):
    response = await call_service(request, "GET", "profile", f"/users/{user_id}/stats")
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
    response = await call_service(request, "GET", "logic", "/games", params=params)
    if response.is_success:
        page = games_page(_payload(response))
        if page is None:
            return error_response(502, "UPSTREAM_ERROR", "Respuesta inesperada del servicio")
        return JSONResponse(status_code=200, content=page)
    return relay(response)


def _is_visible(state: dict[str, Any], user_id: str) -> bool:
    """Regla de visibilidad: participante o partida compartida (shared)."""
    participants = state.get("participants")
    mine = isinstance(participants, list) and any(
        isinstance(p, dict) and p.get("userId") == user_id for p in participants
    )
    return mine or state.get("visibility") == "shared"


@app.get("/games/{game_id}")
async def get_game(game_id: str, request: Request, user_id: str = Depends(current_user)):
    """Detalle de partidas local y vs_bot. Lee Game Logic directamente: solo modos local y
    vs_bot, y solo para participantes o partidas shared (si no, GAME_NOT_FOUND)."""
    if not UUID_RE.match(game_id):
        return error_response(404, "GAME_NOT_FOUND", "La partida no existe o no es visible")
    response = await call_service(request, "GET", "logic", f"/games/{game_id}")
    if not response.is_success or not response.content:
        return relay(response, not_found_code="GAME_NOT_FOUND")
    state = _payload(response)
    if not isinstance(state, dict):
        return error_response(502, "UPSTREAM_ERROR", "Respuesta inesperada del servicio")
    if state.get("mode") not in ("local", "vs_bot") or not _is_visible(state, user_id):
        return error_response(404, "GAME_NOT_FOUND", "La partida no existe o no es visible")
    return JSONResponse(status_code=200, content=state)


@app.get("/matches/{match_id}")
async def get_match(match_id: str, request: Request, user_id: str = Depends(current_user)):
    """Detalle de partidas multiplayer (el id es el matchId, no el gameId). Lee Game Logic
    directamente por matchId, con la misma regla de visibilidad."""
    if not UUID_RE.match(match_id):
        return error_response(404, "MATCH_NOT_FOUND", "La partida no existe o no es visible")
    response = await call_service(request, "GET", "logic", f"/games/by-match/{match_id}")
    if response.status_code == 404:
        # Game Logic responde GAME_NOT_FOUND; para el cliente es una partida (match) inexistente
        return error_response(404, "MATCH_NOT_FOUND", "La partida no existe o no es visible")
    if not response.is_success or not response.content:
        return relay(response, not_found_code="MATCH_NOT_FOUND")
    state = _payload(response)
    if not isinstance(state, dict):
        return error_response(502, "UPSTREAM_ERROR", "Respuesta inesperada del servicio")
    if state.get("mode") != "multiplayer" or not _is_visible(state, user_id):
        return error_response(404, "MATCH_NOT_FOUND", "La partida no existe o no es visible")
    return JSONResponse(status_code=200, content=state)


# --- Inicio: agrega tres servicios, cada sección es independiente ---


def _recent_games(payload: Any) -> list[Any] | None:
    page = games_page(payload)
    return None if page is None else page["items"][:HOME_RECENT_GAMES]


async def _home_section(
    request: Request,
    name: str,
    service: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    extract: Callable[[Any], Any] | None = None,
) -> tuple[str, Any, str | None]:
    """Devuelve (nombre, datos, fallo). fallo: None | 'unreachable' | 'failed'."""
    try:
        response = await call_service(request, "GET", service, path, params=params)
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
        _home_section(request, "profile", "profile", f"/users/{user_id}/profile"),
        _home_section(request, "stats", "profile", f"/users/{user_id}/stats"),
        _home_section(
            request,
            "recentGames",
            "logic",
            "/games",
            params={"userId": user_id, "limit": HOME_RECENT_GAMES},
            extract=_recent_games,
        ),
    )

    # 503 solo si no se puede llegar a ningún servicio (fallan las tres por conexión).
    if all(failure == "unreachable" for _, _, failure in results):
        raise UpstreamUnreachable()

    body: dict[str, Any] = {name: data for name, data, _ in results}
    body["unavailable"] = [name for name, _, failure in results if failure is not None]
    return JSONResponse(status_code=200, content=body)
