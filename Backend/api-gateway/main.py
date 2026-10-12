import asyncio
import json
import os
from typing import Literal
from urllib.parse import urlencode

import httpx
import jwt
import websockets
from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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

USE_MOCK = os.getenv("USE_MOCK", "True").lower() == "true"
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-component:8081")
GAME_SERVICE_URL = os.getenv("GAME_SERVICE_URL", "http://game-service:8083")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


class RegisterData(BaseModel):
    username: str
    password: str = Field(..., min_length=8)


class LoginData(BaseModel):
    username: str
    password: str


class CreateGameData(BaseModel):
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
    raw_token = _jwt_from_request(authorization, token)
    user_id = _user_id_from_jwt(raw_token)

    upstream_headers = []
    if user_id is not None:
        upstream_headers.append(("X-User-Id", user_id))

    upstream_url = _websocket_upstream_url(upstream_path)
    await client_ws.accept()

    try:
        async with websockets.connect(
            upstream_url,
            extra_headers=upstream_headers or None,
            open_timeout=8,
            close_timeout=3,
            max_size=2**20,
        ) as upstream:

            async def browser_to_service():
                try:
                    while True:
                        message = await client_ws.receive_text()
                        await upstream.send(message)
                except (WebSocketDisconnect, asyncio.CancelledError):
                    raise
                except Exception:
                    return

            async def service_to_browser():
                try:
                    async for message in upstream:
                        await client_ws.send_text(message)
                except (WebSocketDisconnect, asyncio.CancelledError):
                    raise
                except Exception:
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
                try:
                    task.result()
                except (WebSocketDisconnect, asyncio.CancelledError):
                    pass
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception:
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
    return {
        "status": "Gateway is running",
        "mode": "Mock" if USE_MOCK else "Production",
        "gameServiceUrl": GAME_SERVICE_URL,
    }


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterData):
    if USE_MOCK:
        if data.username == "existente":
            return custom_error_response(
                409, "USERNAME_TAKEN", "El nombre de usuario ya existe"
            )
        return {
            "userId": "123e4567-e89b-12d3-a456-426614174000",
            "username": data.username,
        }

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{AUTH_SERVICE_URL}/auth/register", json=data.dict()
            )
            return JSONResponse(status_code=res.status_code, content=_json_or_text(res))
        except httpx.RequestError:
            return custom_error_response(
                503, "SERVICE_UNAVAILABLE", "Auth Service no disponible"
            )


@app.post("/auth/login")
async def login(data: LoginData):
    if USE_MOCK:
        if data.password == "wrong":
            return custom_error_response(
                401, "INVALID_CREDENTIALS", "Usuario o contraseña incorrectos"
            )
        return {
            "accessToken": "mocked_jwt_token_12345",
            "expiresIn": 3600,
            "user": {
                "userId": "123e4567-e89b-12d3-a456-426614174000",
                "username": data.username,
            },
        }

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(f"{AUTH_SERVICE_URL}/auth/login", json=data.dict())
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


@app.post("/games", status_code=status.HTTP_201_CREATED)
async def create_game(data: CreateGameData, authorization: str | None = Header(None)):
    if USE_MOCK:
        moves = []
        if data.mode == "vs_bot" and data.playerColor == "black":
            moves.append({"from": "e2", "to": "e4", "by": "bot"})
        return {
            "gameId": "game_mock_999",
            "mode": data.mode,
            "level": data.level,
            "playerColor": data.playerColor,
            "status": "IN_PROGRESS",
            "moves": moves,
            "createdAt": "2026-10-11T14:00:00Z",
        }
    return custom_error_response(
        400,
        "WEBSOCKET_PROTOCOL_REQUIRED",
        "Crea la partida mediante el mensaje create_game en /ws/game.",
    )


@app.get("/games")
async def list_games(authorization: str | None = Header(None)):
    if USE_MOCK:
        return [
            {
                "gameId": "game_mock_999",
                "mode": "vs_bot",
                "status": "IN_PROGRESS",
                "result": None,
                "createdAt": "2026-10-11T14:00:00Z",
            },
            {
                "gameId": "game_mock_888",
                "mode": "local",
                "status": "FINISHED",
                "result": "white_win",
                "createdAt": "2026-10-10T10:00:00Z",
            },
        ]
    return custom_error_response(
        501,
        "ENDPOINT_NOT_SUPPORTED",
        "Game Service no documenta un endpoint HTTP para listar partidas.",
    )


@app.get("/games/{game_id}")
async def get_game(game_id: str, authorization: str | None = Header(None)):
    if USE_MOCK:
        if game_id == "404":
            return custom_error_response(404, "GAME_NOT_FOUND", "La partida no existe")
        return {
            "gameId": game_id,
            "mode": "vs_bot",
            "status": "IN_PROGRESS",
            "result": None,
            "moves": [{"from": "e2", "to": "e4"}],
            "createdAt": "2026-10-11T14:00:00Z",
        }
    return custom_error_response(
        501,
        "ENDPOINT_NOT_SUPPORTED",
        "Game Service no documenta un endpoint HTTP para consultar partidas.",
    )


@app.post("/games/{game_id}/resign")
async def resign_game(
    game_id: str, data: ResignData, authorization: str | None = Header(None)
):
    if USE_MOCK:
        if game_id == "finished":
            return custom_error_response(
                422, "GAME_FINISHED", "La partida ya ha finalizado"
            )
        return {
            "gameId": game_id,
            "status": "FINISHED",
            "result": "resigned",
            "resignedSide": data.side,
        }
    return custom_error_response(
        400,
        "WEBSOCKET_PROTOCOL_REQUIRED",
        "Abandona la partida enviando el mensaje resign por /ws/game.",
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
