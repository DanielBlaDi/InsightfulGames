import os
from typing import Literal

import httpx
from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI()

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
GAME_SERVICE_URL = os.getenv("GAME_SERVICE_URL", "http://game-service:8082")


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
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


@app.get("/health")
def health_check():
    return {
        "status": "Gateway is running",
        "mode": "Mock" if USE_MOCK else "Production",
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
    else:
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"{AUTH_SERVICE_URL}/auth/register", json=data.dict()
                )
                return JSONResponse(status_code=res.status_code, content=res.json())
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
    else:
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"{AUTH_SERVICE_URL}/auth/login", json=data.dict()
                )
                return JSONResponse(status_code=res.status_code, content=res.json())
            except httpx.RequestError:
                return custom_error_response(
                    503, "SERVICE_UNAVAILABLE", "Auth Service no disponible"
                )


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
    else:
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": authorization} if authorization else {}
            try:
                res = await client.post(
                    f"{GAME_SERVICE_URL}/games", json=data.dict(), headers=headers
                )
                return JSONResponse(status_code=res.status_code, content=res.json())
            except httpx.RequestError:
                return custom_error_response(
                    503, "SERVICE_UNAVAILABLE", "Game Service no disponible"
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
    else:
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": authorization} if authorization else {}
            try:
                res = await client.get(f"{GAME_SERVICE_URL}/games", headers=headers)
                return JSONResponse(status_code=res.status_code, content=res.json())
            except httpx.RequestError:
                return custom_error_response(
                    503, "SERVICE_UNAVAILABLE", "Game Service no disponible"
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
    else:
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": authorization} if authorization else {}
            try:
                res = await client.get(
                    f"{GAME_SERVICE_URL}/games/{game_id}", headers=headers
                )
                return JSONResponse(status_code=res.status_code, content=res.json())
            except httpx.RequestError:
                return custom_error_response(
                    503, "SERVICE_UNAVAILABLE", "Game Service no disponible"
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
    else:
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": authorization} if authorization else {}
            try:
                res = await client.post(
                    f"{GAME_SERVICE_URL}/games/{game_id}/resign",
                    json=data.dict(),
                    headers=headers,
                )
                return JSONResponse(status_code=res.status_code, content=res.json())
            except httpx.RequestError:
                return custom_error_response(
                    503, "SERVICE_UNAVAILABLE", "Game Service no disponible"
                )


@app.websocket("/ws/games/{game_id}")
async def game_websocket(websocket: WebSocket, game_id: str, token: str | None = None):
    if not token:
        await websocket.close(code=4401, reason="Token requerido")
        return

    await websocket.accept()

    if USE_MOCK:
        await websocket.send_json(
            {
                "type": "state",
                "state": {
                    "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                    "turn": "black",
                    "legalMoves": {"e7": ["e5", "e6"]},
                    "moves": [{"from": "e2", "to": "e4", "san": "e4"}],
                    "status": "IN_PROGRESS",
                    "result": None,
                    "endReason": None,
                    "mode": "vs_bot",
                    "playerColor": "white",
                    "botLevel": 1,
                },
                "lastMove": "e2e4",
            }
        )
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("type") == "move":
                    pass
        except WebSocketDisconnect:
            pass
    else:
        pass
