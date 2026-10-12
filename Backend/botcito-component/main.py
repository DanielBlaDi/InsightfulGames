"""API sin estado para consultar Stockfish mediante UCI."""

import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import Literal

import chess
import chess.engine
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("botcito")


class BotError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class MoveRequest(BaseModel):
    fen: str = Field(min_length=1, max_length=200, strict=True)
    level: int = Field(ge=1, le=20, strict=True)


class Evaluation(BaseModel):
    type: Literal["cp", "mate"]
    value: int


class MoveResponse(BaseModel):
    uci: str
    san: str
    evaluation: Evaluation


class LegacyMoveResponse(MoveResponse):
    move: str


def parse_position(fen: str) -> chess.Board:
    try:
        if len(fen.split()) != 6:
            raise ValueError("Se requieren los seis campos FEN")
        board = chess.Board(fen)
        if not board.is_valid():
            raise ValueError("Posición inválida")
    except ValueError as exc:
        raise BotError(400, "INVALID_FEN", "La posición FEN no es válida.") from exc
    if not any(board.legal_moves):
        raise BotError(422, "NO_LEGAL_MOVES", "La posición no tiene jugadas legales.")
    return board


class StockfishEngine:
    """Un proceso por worker; exclusión mutua para no mezclar consultas UCI."""

    def __init__(self):
        self.path = os.getenv("STOCKFISH_PATH", "/usr/games/stockfish")
        self.lock = threading.Lock()
        self.engine: chess.engine.SimpleEngine | None = None

    def start(self, startup_timeout: float = 5.0):
        self.engine = chess.engine.SimpleEngine.popen_uci(self.path, timeout=startup_timeout)
        try:
            self.engine.configure({"Threads": 1, "Hash": 32, "UCI_LimitStrength": False})
            # Arrancar en Docker puede tardar más que una consulta normal.
            self.engine.timeout = 2.0
        except Exception:
            self.close()
            raise

    def close(self):
        if self.engine is not None:
            self.engine.close()
            self.engine = None

    def healthy(self) -> bool:
        engine = self.engine
        return engine is not None and not engine.returncode.done()

    def best_move(self, board: chess.Board, level: int) -> MoveResponse:
        # No cola ilimitada: una petición concurrente recibe un error recuperable.
        if not self.lock.acquire(blocking=False):
            raise BotError(503, "ENGINE_BUSY", "El motor está ocupado; intenta nuevamente.")
        try:
            if not self.healthy():
                self.close()
                self.start()
            assert self.engine is not None
            self.engine.configure({"Skill Level": level})
            result = self.engine.play(board, chess.engine.Limit(time=0.3), game=object())
            move = result.move
            if move is None or move not in board.legal_moves:
                raise RuntimeError("Stockfish no devolvió una jugada legal")
            # Evalúa la jugada elegida, con fuerza completa, desde el turno de entrada.
            # No reutiliza el score de play: a niveles bajos puede ser de otra variante.
            info = self.engine.analyse(
                board, chess.engine.Limit(time=0.2), root_moves=[move],
                options={"Skill Level": 20}, game=object(),
            )
            score = info["score"].pov(board.turn)
            value = score.mate() if score.is_mate() else score.score()
            if value is None:
                raise RuntimeError("Stockfish no devolvió una evaluación")
            return MoveResponse(
                uci=move.uci(), san=board.san(move),
                evaluation=Evaluation(type="mate" if score.is_mate() else "cp", value=value),
            )
        except Exception as exc:
            logger.exception("Falló la consulta a Stockfish")
            self.close()  # La siguiente petición intentará iniciar un proceso nuevo.
            raise BotError(503, "ENGINE_UNAVAILABLE", "El motor no está disponible.") from exc
        finally:
            self.lock.release()


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = StockfishEngine()
    engine.start(startup_timeout=30.0)  # Margen para el arranque conjunto en Docker.
    app.state.engine = engine
    try:
        yield
    finally:
        engine.close()


app = FastAPI(title="Botcito — Stockfish", version="1.0.0", lifespan=lifespan)


@app.exception_handler(BotError)
async def bot_error_handler(_request: Request, exc: BotError):
    return JSONResponse(status_code=exc.status, content={
        "error": {"code": exc.code, "message": exc.message}
    })


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, _exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": {
        "code": "VALIDATION_ERROR",
        "message": "Envía fen como texto y level como entero entre 1 y 20.",
    }})


@app.get("/health")
def health(request: Request):
    if not request.app.state.engine.healthy():
        raise BotError(503, "ENGINE_UNAVAILABLE", "El motor no está disponible.")
    return {"status": "ok"}


@app.post("/engine/best-move", response_model=MoveResponse)
def best_move(data: MoveRequest, request: Request):
    return request.app.state.engine.best_move(parse_position(data.fen), data.level)


@app.post("/best-move", response_model=LegacyMoveResponse)
def legacy_best_move(data: MoveRequest, request: Request):
    """Compatibilidad con BotcitoClient.java: conserva move sin perder la evaluación."""
    result = best_move(data, request)
    return LegacyMoveResponse(**result.model_dump(), move=result.uci)
