import asyncio
import logging
import os
from typing import Literal
from urllib.parse import urlencode

import httpx
import jwt
import websockets
from fastapi import FastAPI, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

# Config

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("arquisoft.gateway")

app = FastAPI(title="ArquiSoft API Gateway")

AUTH_URL = os.getenv(
    "AUTH_URL",
    os.getenv("AUTH_SERVICE_URL", "http://auth-component:8081"),
).rstrip("/")

SINGLE_PLAYER_URL = os.getenv(
    "SINGLE_PLAYER_URL",
    os.getenv("GAME_SERVICE_URL", "http://single-player-component:8083"),
).rstrip("/")

BOTCITO_URL = os.getenv("BOTCITO_URL", "http://botcito-component:8086").rstrip("/")

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Mapeos de entrada


class RegisterData(BaseModel):
    username: str = Field(..., min_length=3, max_length=20)
    password: str = Field(..., min_length=8)


class LoginData(BaseModel):
    username: str = Field(..., min_length=3, max_length=20)
    password: str = Field(..., min_length=1)


class CreateGameData(BaseModel):
    mode: Literal["local", "vs_bot"]
    level: int | None = Field(None, ge=1, le=20)
    playerColor: Literal["white", "black"] | None = None


class ResignData(BaseModel):
    side: Literal["white", "black"] | None = None


class BestMoveData(BaseModel):
    fen: str = Field(..., min_length=1)
    level: int = Field(..., ge=1, le=20)


# Errores


def error_response(
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
):
    logger.info("Validación fallida: %s", request.url.path)

    return error_response(
        400,
        "VALIDATION_ERROR",
        "Campos faltantes o con formato inválido",
    )


# JWT


def _jwt_from_authorization(
    authorization: str | None,
) -> str | None:
    if not authorization:
        return None

    scheme, separator, token = authorization.partition(" ")

    if separator and scheme.lower() == "bearer" and token.strip():
        return token.strip()

    return None


def _user_id_from_jwt(token: str | None) -> str | None:
    if not token or not JWT_SECRET:
        return None

    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError:
        return None

    # El contrato define "sub" como el userId
    user_id = claims.get("sub")

    if not isinstance(user_id, str) or not user_id.strip():
        return None

    return user_id


def _require_user(
    authorization: str | None,
) -> tuple[str | None, JSONResponse | None]:
    token = _jwt_from_authorization(authorization)
    user_id = _user_id_from_jwt(token)

    if user_id is None:
        return (
            None,
            error_response(
                401,
                "UNAUTHORIZED",
                "Token ausente, inválido o vencido",
            ),
        )

    return user_id, None


# HTTP Tools


def _json_or_text(response: httpx.Response):
    try:
        return response.json()
    except ValueError:
        return {"message": response.text} if response.text else None


def _error_payload_for_upstream(
    status_code: int,
    payload,
):
    """Normaliza errores no estructurados de los servicios destino."""
    if (
        isinstance(payload, dict)
        and isinstance(payload.get("error"), dict)
        and payload["error"].get("code")
        and payload["error"].get("message")
    ):
        return payload

    mapping = {
        400: (
            "VALIDATION_ERROR",
            "Campos faltantes o con formato inválido",
        ),
        401: ("UNAUTHORIZED", "Token ausente, inválido o vencido"),
        404: ("GAME_NOT_FOUND", "La partida no existe o no pertenece al usuario"),
        409: ("USERNAME_TAKEN", "El nombre de usuario ya existe"),
        422: ("INVALID_MOVE", "La solicitud no se pudo procesar"),
    }

    code, message = mapping.get(
        status_code,
        ("UPSTREAM_ERROR", "El servicio destino devolvió un error"),
    )

    return {
        "error": {
            "code": code,
            "message": message,
        }
    }


async def _forward_http(
    method: str,
    base_url: str,
    path: str,
    request: Request,
    user_id: str | None = None,
    json_body=None,
):
    """
    Reenvía una petición HTTP al servicio correspondiente.

    No acepta X-User-Id del cliente como fuente de identidad.
    La identidad solo se añade después de verificar el JWT.
    """
    url = f"{base_url}{path}"

    if request.url.query:
        url += f"?{request.url.query}"

    headers = {}

    content_type = request.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type

    accept = request.headers.get("accept")
    if accept:
        headers["Accept"] = accept

    if user_id:
        headers["X-User-Id"] = user_id

    try:
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            follow_redirects=False,
        ) as client:
            if json_body is not None:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                )
            else:
                body = await request.body() if method not in ("GET", "HEAD") else None

                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    content=body,
                )

        logger.info(
            "%s %s -> %s (%s)",
            method,
            path,
            base_url,
            response.status_code,
        )

        if response.status_code == 204 or not response.content:
            return Response(status_code=response.status_code)

        payload = _json_or_text(response)

        if response.is_error:
            payload = _error_payload_for_upstream(
                response.status_code,
                payload,
            )

        return JSONResponse(
            status_code=response.status_code,
            content=payload,
        )

    except httpx.TimeoutException:
        logger.error("Timeout al contactar %s", base_url)

        return error_response(
            503,
            "SERVICE_UNAVAILABLE",
            "El servicio destino no respondió a tiempo",
        )

    except httpx.RequestError:
        logger.exception("Error de conexión con %s", base_url)

        return error_response(
            503,
            "SERVICE_UNAVAILABLE",
            "Servicio destino no disponible",
        )


# Health


@app.get("/health")
async def health_check():
    return {"status": "ok"}


# Auth


@app.post("/auth/register", status_code=201)
async def register(data: RegisterData):
    logger.info("POST /auth/register")

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{AUTH_URL}/auth/register",
                json=data.model_dump(),
            )

        payload = _json_or_text(response)

        if response.status_code == 409:
            payload = _error_payload_for_upstream(409, payload)
        elif response.status_code == 400:
            payload = _error_payload_for_upstream(400, payload)

        return JSONResponse(
            status_code=response.status_code,
            content=payload,
        )

    except httpx.RequestError:
        logger.exception("Auth Service no disponible durante registro")

        return error_response(
            503,
            "SERVICE_UNAVAILABLE",
            "Auth Service no disponible",
        )


@app.post("/auth/login")
async def login(data: LoginData):
    logger.info("POST /auth/login")

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{AUTH_URL}/auth/login",
                json=data.model_dump(),
            )

        payload = _json_or_text(response)

        if response.status_code == 401:
            payload = _error_payload_for_upstream(
                401,
                payload
                if isinstance(payload, dict) and isinstance(payload.get("error"), dict)
                else {
                    "error": {
                        "code": "INVALID_CREDENTIALS",
                        "message": "Usuario o contraseña incorrectos",
                    }
                },
            )

            # INVALID_CREDENTIALS es el código contractual de login.
            if not isinstance(_json_or_text(response), dict) or not isinstance(
                _json_or_text(response).get("error"),
                dict,
            ):
                payload = {
                    "error": {
                        "code": "INVALID_CREDENTIALS",
                        "message": "Usuario o contraseña incorrectos",
                    }
                }

        elif response.status_code == 400:
            payload = _error_payload_for_upstream(400, payload)

        return JSONResponse(
            status_code=response.status_code,
            content=payload,
        )

    except httpx.RequestError:
        logger.exception("Auth Service no disponible durante login")

        return error_response(
            503,
            "SERVICE_UNAVAILABLE",
            "Auth Service no disponible",
        )


@app.delete("/auth/account", status_code=204)
async def delete_account(
    request: Request,
    authorization: str | None = Header(default=None),
):
    user_id, error = _require_user(authorization)

    if error:
        return error

    return await _forward_http(
        "DELETE",
        AUTH_URL,
        "/auth/account",
        request,
        user_id=user_id,
    )


# Single Player


@app.post("/games", status_code=201)
async def create_game(
    data: CreateGameData,
    request: Request,
    authorization: str | None = Header(default=None),
):
    user_id, error = _require_user(authorization)

    if error:
        return error

    # El contrato exige level y playerColor únicamente para vs_bot
    if data.mode == "vs_bot" and (data.level is None or data.playerColor is None):
        return error_response(
            400,
            "VALIDATION_ERROR",
            "El modo vs_bot requiere level y playerColor",
        )

    if data.mode == "local" and (
        data.level is not None or data.playerColor is not None
    ):
        return error_response(
            400,
            "VALIDATION_ERROR",
            "level y playerColor solo se permiten en modo vs_bot",
        )

    body = {
        "mode": data.mode,
    }

    if data.mode == "vs_bot":
        body["level"] = data.level
        body["playerColor"] = data.playerColor

    logger.info("POST /games mode=%s", data.mode)

    return await _forward_http(
        "POST",
        SINGLE_PLAYER_URL,
        "/games",
        request,
        user_id=user_id,
        json_body=body,
    )


@app.get("/games")
async def list_games(
    request: Request,
    authorization: str | None = Header(default=None),
):
    user_id, error = _require_user(authorization)

    if error:
        return error

    return await _forward_http(
        "GET",
        SINGLE_PLAYER_URL,
        "/games",
        request,
        user_id=user_id,
    )


@app.get("/games/{game_id}")
async def get_game(
    game_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    user_id, error = _require_user(authorization)

    if error:
        return error

    return await _forward_http(
        "GET",
        SINGLE_PLAYER_URL,
        f"/games/{game_id}",
        request,
        user_id=user_id,
    )


@app.post("/games/{game_id}/resign")
async def resign_game(
    game_id: str,
    data: ResignData,
    request: Request,
    authorization: str | None = Header(default=None),
):
    user_id, error = _require_user(authorization)

    if error:
        return error

    return await _forward_http(
        "POST",
        SINGLE_PLAYER_URL,
        f"/games/{game_id}/resign",
        request,
        user_id=user_id,
        json_body=data.model_dump(exclude_none=True),
    )


# Catch-all para cualquier otra ruta /games/* del contrato
# Las rutas anteriores tienen prioridad
@app.api_route(
    "/games/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def games_proxy(
    path: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    user_id, error = _require_user(authorization)

    if error:
        return error

    return await _forward_http(
        request.method,
        SINGLE_PLAYER_URL,
        f"/games/{path}",
        request,
        user_id=user_id,
    )


# Bot


@app.post("/engine/best-move")
async def best_move(
    data: BestMoveData,
    request: Request,
):
    logger.info("POST /engine/best-move level=%s", data.level)

    return await _forward_http(
        "POST",
        BOTCITO_URL,
        "/engine/best-move",
        request,
        json_body=data.model_dump(),
    )


@app.api_route(
    "/engine/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def engine_proxy(
    path: str,
    request: Request,
):
    # Segun el contrato, el bot está en una ruta pública
    return await _forward_http(
        request.method,
        BOTCITO_URL,
        f"/engine/{path}",
        request,
    )


# WebSocket, Proxy a Single Player


def _ws_url(base_url: str, path: str, query: str = "") -> str:
    base = base_url.rstrip("/")

    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]

    result = f"{base}{path}"

    if query:
        result += f"?{query}"

    return result


async def _connect_upstream_websocket(url: str, user_id: str):
    """
    Compatibilidad con distintas versiones de la librería websockets.
    """
    headers = [("X-User-Id", user_id)]

    try:
        connection = websockets.connect(
            url,
            extra_headers=headers,
            open_timeout=8,
            close_timeout=3,
            max_size=2**20,
        )
    except TypeError:
        connection = websockets.connect(
            url,
            additional_headers=headers,
            open_timeout=8,
            close_timeout=3,
            max_size=2**20,
        )

    return connection


async def _proxy_websocket(
    client_ws: WebSocket,
    game_id: str,
):
    await client_ws.accept()

    raw_token = client_ws.query_params.get("token")
    user_id = _user_id_from_jwt(raw_token)

    if user_id is None:
        logger.warning("WebSocket rechazado: token inválido o ausente")
        await client_ws.close(
            code=4401,
            reason="Token inválido o vencido",
        )
        return

    upstream_url = _ws_url(
        SINGLE_PLAYER_URL,
        f"/ws/games/{game_id}",
        urlencode({"token": raw_token}),
    )

    logger.info("Conectando WebSocket de partida %s", game_id)

    try:
        connection = await _connect_upstream_websocket(
            upstream_url,
            user_id,
        )

        async with connection as upstream:

            async def client_to_upstream():
                while True:
                    message = await client_ws.receive_text()
                    await upstream.send(message)

            async def upstream_to_client():
                async for message in upstream:
                    await client_ws.send_text(message)

            tasks = [
                asyncio.create_task(client_to_upstream()),
                asyncio.create_task(upstream_to_client()),
            ]

            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            await asyncio.gather(
                *pending,
                return_exceptions=True,
            )

            for task in done:
                try:
                    task.result()
                except (
                    WebSocketDisconnect,
                    asyncio.CancelledError,
                ):
                    pass

    except WebSocketDisconnect:
        logger.info("Cliente desconectado de partida %s", game_id)

    except Exception as exc:  # noqa: BLE001
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)

        if status_code is None:
            status_code = getattr(exc, "status_code", None)

        logger.warning(
            "Error en WebSocket de partida %s: %s",
            game_id,
            type(exc).__name__,
        )

        try:
            if status_code in (401, 403):
                await client_ws.close(
                    code=4401,
                    reason="Token inválido o vencido",
                )
            elif status_code == 404:
                await client_ws.close(
                    code=4404,
                    reason="Partida inexistente o ajena",
                )
            else:
                await client_ws.close(
                    code=1011,
                    reason="Servicio de partidas no disponible",
                )
        except Exception as e:  # noqa: BLE001
            logger.info("Error desconocido: %s", e)


@app.websocket("/ws/games/{game_id}")
async def game_websocket(
    websocket: WebSocket,
    game_id: str,
):
    await _proxy_websocket(websocket, game_id)
