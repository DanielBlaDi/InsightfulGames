import asyncio
import logging
import os
from typing import Literal

import httpx
import jwt
import websockets
from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("arquis oft.gateway".replace(" ", ""))

app = FastAPI(title="ArquiSoft API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-component:8081")
# Game Service / Single Player is documented on port 8083 (not Game Logic's 8082).
GAME_SERVICE_URL = os.getenv("GAME_SERVICE_URL", "http://game-service:8083")
# Configure this with the same signing secret/algorithm as Auth before relying on JWT identity.
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


class RegisterData(BaseModel):
    username: str
    password: str = Field(..., min_length=8)


class LoginData(BaseModel):
    username: str
    password: str


class CreateGameData(BaseModel):
    # Legacy HTTP shape retained for compatibility with the existing frontend.
    mode: Literal["local", "vs_bot"]
    level: int | None = Field(None, ge=1, le=20)
    playerColor: Literal["white", "black"] | None = None


class ResignData(BaseModel):
    side: Literal["white", "black"] | None = None


def custom_error_response(status_code: int, code: str, message: str):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _jwt_from_request(authorization: str | None, token: str | None) -> str | None:
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            return value
    return token


def _user_id_from_jwt(raw_token: str | None) -> str | None:
    """Return a user ID only after signature verification; never trust a client-supplied X-User-Id."""
    if not raw_token or not JWT_SECRET:
        return None

    try:
        claims = jwt.decode(raw_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None

    value = claims.get("userId", claims.get("user_id", claims.get("sub")))
    return str(value) if value is not None else None


def _websocket_upstream_url(path: str) -> str:
    base_url = GAME_SERVICE_URL.rstrip("/")
    if base_url.startswith("https://"):
        base_url = "wss://" + base_url[len("https://") :]
    elif base_url.startswith("http://"):
        base_url = "ws://" + base_url[len("http://") :]
    return f"{base_url}{path}"


async def _proxy_websocket(
    client_ws: WebSocket,
    upstream_path: str,
    authorization: str | None = None,
    token: str | None = None,
):
    logger.info("WebSocket: iniciando proxy hacia %s", upstream_path)
    raw_token = _jwt_from_request(authorization, token)
    user_id = _user_id_from_jwt(raw_token)
    logger.info(
        "WebSocket: identidad %s",
        "verificada" if user_id is not None else "no disponible",
    )

    # The browser controls its own headers; only this server creates X-User-Id,
    # and only from a JWT whose signature was verified.
    upstream_headers = []
    if user_id is not None:
        upstream_headers.append(("X-User-Id", user_id))

    upstream_url = _websocket_upstream_url(upstream_path)
    logger.info("WebSocket: conectando con Game Service en %s", upstream_url)
    await client_ws.accept()

    try:
        async with websockets.connect(
            upstream_url,
            extra_headers=upstream_headers or None,
            open_timeout=8,
            close_timeout=3,
            max_size=2**20,
        ) as upstream:
            logger.info("WebSocket: conexión con Game Service establecida")

            async def browser_to_service():
                try:
                    while True:
                        message = await client_ws.receive_text()
                        logger.debug("WebSocket: mensaje recibido del navegador")
                        # Preserve the Single Player JSON protocol exactly.
                        await upstream.send(message)
                except (WebSocketDisconnect, asyncio.CancelledError):
                    logger.info("WebSocket: navegador desconectado")
                    raise
                except Exception:
                    logger.exception("WebSocket: error reenviando mensaje al servicio")
                    return

            async def service_to_browser():
                try:
                    async for message in upstream:
                        # Game Service sends JSON text messages: game_created,
                        # game_state, game_over, and error.
                        logger.debug("WebSocket: mensaje recibido de Game Service")
                        await client_ws.send_text(message)
                except (WebSocketDisconnect, asyncio.CancelledError):
                    logger.info("WebSocket: cliente desconectado durante el envío")
                    raise
                except Exception:
                    logger.exception("WebSocket: error enviando mensaje al navegador")
                    return

            tasks = [
                asyncio.create_task(browser_to_service()),
                asyncio.create_task(service_to_browser()),
            ]
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                # Consume exceptions to avoid "Task exception was never retrieved".
                try:
                    task.result()
                except (WebSocketDisconnect, asyncio.CancelledError):
                    pass
                except Exception:
                    pass
    except WebSocketDisconnect:
        logger.info("WebSocket: conexión cerrada por el cliente")
    except Exception:
        logger.exception(
            "WebSocket: no fue posible conectar o mantener la conexión con Game Service"
        )
        # Avoid leaking internal service details to the browser.
        try:
            await client_ws.send_json(
                {
                    "type": "error",
                    "message": "No fue posible conectar con Game Service",
                }
            )
            await client_ws.close(code=1011, reason="Game Service no disponible")
        except Exception:
            pass


@app.get("/health")
def health_check():
    logger.info("HTTP GET /health")
    return {
        "status": "Gateway is running",
        "gameServiceUrl": GAME_SERVICE_URL,
    }


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterData):
    logger.info("HTTP POST /auth/register: iniciando registro")
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{AUTH_SERVICE_URL}/auth/register", json=data.model_dump()
            )
            logger.info("Auth Service: registro respondió con HTTP %s", res.status_code)
            return JSONResponse(status_code=res.status_code, content=_json_or_text(res))
        except httpx.RequestError:
            logger.exception("Auth Service: error de conexión durante el registro")
            return custom_error_response(
                503, "SERVICE_UNAVAILABLE", "Auth Service no disponible"
            )


@app.post("/auth/login")
async def login(data: LoginData):
    logger.info("HTTP POST /auth/login: iniciando inicio de sesión")
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{AUTH_SERVICE_URL}/auth/login", json=data.model_dump()
            )
            return JSONResponse(status_code=res.status_code, content=_json_or_text(res))
        except httpx.RequestError:
            return custom_error_response(
                503, "SERVICE_UNAVAILABLE", "Auth Service no disponible"
            )


def _json_or_text(response: httpx.Response):
    try:
        return response.json()
    except ValueError:
        return {"message": response.text}


# Legacy HTTP routes remain for compatibility, but Single Player's documented
# contract is WebSocket-first. Do not simulate game operations over HTTP.
@app.post("/games", status_code=status.HTTP_201_CREATED)
async def create_game(data: CreateGameData, authorization: str | None = Header(None)):
    logger.warning("HTTP POST /games: operación no disponible en el contrato HTTP")
    return custom_error_response(
        501,
        "HTTP_GAME_API_NOT_IN_CONTRACT",
        "Single Player expone el protocolo WebSocket /ws/game; esta ruta HTTP requiere un contrato confirmado.",
    )


@app.get("/games")
async def list_games(authorization: str | None = Header(None)):
    logger.warning("HTTP GET /games: operación no disponible en el contrato HTTP")
    return custom_error_response(
        501,
        "HTTP_GAME_API_NOT_IN_CONTRACT",
        "Single Player no documenta una ruta HTTP para listar partidas.",
    )


@app.get("/games/{game_id}")
async def get_game(game_id: str, authorization: str | None = Header(None)):
    logger.warning(
        "HTTP GET /games/%s: operación no disponible en el contrato HTTP", game_id
    )
    return custom_error_response(
        501,
        "HTTP_GAME_API_NOT_IN_CONTRACT",
        "Single Player no documenta una ruta HTTP para consultar partidas.",
    )


@app.post("/games/{game_id}/resign")
async def resign_game(
    game_id: str,
    data: ResignData,
    authorization: str | None = Header(None),
):
    logger.warning(
        "HTTP POST /games/%s/resign: operación no disponible en el contrato HTTP",
        game_id,
    )
    return custom_error_response(
        501,
        "HTTP_GAME_API_NOT_IN_CONTRACT",
        "El abandono se envía por WebSocket con el mensaje type=resign.",
    )


@app.websocket("/ws/game")
async def game_websocket(
    websocket: WebSocket,
    authorization: str | None = Header(None),
    token: str | None = None,
):
    """Proxy for the documented Game Service endpoint /ws/game."""
    await _proxy_websocket(websocket, "/ws/game", authorization, token)


@app.websocket("/ws/games/{game_id}")
async def legacy_game_websocket(
    websocket: WebSocket,
    game_id: str,
    authorization: str | None = Header(None),
    token: str | None = None,
):
    """Compatibility route: forwards to /ws/game; game creation remains message-driven."""
    await _proxy_websocket(websocket, "/ws/game", authorization, token)
