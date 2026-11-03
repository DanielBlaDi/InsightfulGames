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

class InternalMoveRequest(BaseModel):
    fen: str = Field(min_length=1, max_length=200, strict=True)
    botLevel: int = Field(ge=1, le=20, strict=True)

class Evaluation(BaseModel):
    type: Literal["cp", "mate"]
    value: int


class MoveResponse(BaseModel):
    uci: str
    san: str
    evaluation: Evaluation

class InternalEvaluation(Evaluation):
    perspective: Literal["side_to_move"] = "side_to_move"

class InternalMoveResponse(BaseModel):
    uci: str
    san: str
    evaluation: InternalEvaluation

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

class EngineSlot:
    """Representa un motor Stockfish independiente."""

    def __init__(self):
        self.engine: chess.engine.SimpleEngine | None = None
        self.lock = threading.Lock()

class StockfishEngine:
    """Un proceso por worker; exclusión mutua para no mezclar consultas UCI."""

    def __init__(self):
        self.path = os.getenv("STOCKFISH_PATH", "/usr/games/stockfish")

        self.engine_threads = int(os.getenv("ENGINE_THREADS", "1"))
        self.engine_timeout_ms = int(os.getenv("ENGINE_TIMEOUT_MS", "2000"))
        self.pool_size = int(os.getenv("ENGINE_POOL_SIZE", "2"))

        if (
            self.engine_threads < 1
            or self.engine_timeout_ms < 1
            or self.pool_size < 1
        ):
            raise ValueError("La configuración del motor debe ser positiva.")

        self.lock = threading.Lock()
        self.engine: chess.engine.SimpleEngine | None = None
        self.slots = [EngineSlot() for _ in range(self.pool_size)]


    def _create_engine(self, startup_timeout: float):
        """Inicia y configura un proceso independiente de Stockfish."""

        engine = chess.engine.SimpleEngine.popen_uci(
            self.path,
            timeout=startup_timeout
        )

        try:
            engine.configure({
                "Threads": self.engine_threads,
                "Hash": 32,
                "UCI_LimitStrength": False
            })

            engine.timeout = self.engine_timeout_ms / 1000

            return engine

        except Exception:
            engine.close()
            raise

    def start(self, startup_timeout: float = 5.0):
        """Inicia todos los motores del pool."""

        self.close()

        try:
            for slot in self.slots:
                slot.engine = self._create_engine(startup_timeout)

            # Compatibilidad temporal con el codigo anterior.
            self.engine = self.slots[0].engine

        except Exception:
            self.close()
            raise

    def close(self):
        """Cierra todos los procesos Stockfish del pool."""

        for slot in self.slots:
            if slot.engine is not None:
                try:
                    slot.engine.close()
                except Exception:
                    logger.exception("Error al cerrar Stockfish")
                finally:
                    slot.engine = None

        self.engine = None

    def healthy(self) -> bool:
        engine = self.engine
        return engine is not None and not engine.returncode.done()

    def _acquire_slot(self) -> EngineSlot:
        """Reserva un motor disponible sin esperar."""

        for slot in self.slots:
            if slot.lock.acquire(blocking=False):
                return slot

        raise BotError(
            503,
            "ENGINE_BUSY",
            "Todos los motores estan ocupados; intenta nuevamente."
        )

    def _discard_slot(self, slot: EngineSlot):
        """Cierra únicamente el motor del espacio indicado."""

        engine = slot.engine
        slot.engine = None

        if slot is self.slots[0]:
            self.engine = None

        if engine is not None:
            try:
                engine.close()
            except Exception:
                logger.exception("Error al cerrar un motor Stockfish")


    def best_move(self, board: chess.Board, level: int) -> MoveResponse:
        """Calcula una jugada utilizando un motor disponible del pool."""

        slot = self._acquire_slot()

        try:
            engine = slot.engine

            # Recuperar solamente el motor que haya fallado.
            if engine is None or engine.returncode.done():
                self._discard_slot(slot)
                engine = self._create_engine(5.0)
                slot.engine = engine

                if slot is self.slots[0]:
                    self.engine = engine

            # Configurar la dificultad.
            engine.configure({"Skill Level": level})

            # Calcular la mejor jugada.
            result = engine.play(
                board,
                chess.engine.Limit(time=0.3),
                game=object()
            )

            move = result.move

            if move is None or move not in board.legal_moves:
                raise RuntimeError(
                    "Stockfish no devolvio una jugada legal"
                )

            # Evaluar la jugada seleccionada.
            info = engine.analyse(
                board,
                chess.engine.Limit(time=0.2),
                root_moves=[move],
                options={"Skill Level": 20},
                game=object()
            )

            score = info["score"].pov(board.turn)

            value = (
                score.mate()
                if score.is_mate()
                else score.score()
            )

            if value is None:
                raise RuntimeError(
                    "Stockfish no devolvio una evaluacion"
                )

            return MoveResponse(
                uci=move.uci(),
                san=board.san(move),
                evaluation=Evaluation(
                    type="mate" if score.is_mate() else "cp",
                    value=value
                )
            )

        except TimeoutError as exc:
            logger.exception("Timeout de Stockfish")
            self._discard_slot(slot)

            raise BotError(
                504,
                "ENGINE_TIMEOUT",
                "El motor supero el tiempo permitido."
            ) from exc

        except Exception as exc:
            logger.exception("Fallo la consulta a Stockfish")
            self._discard_slot(slot)

            raise BotError(
                503,
                "SERVICES_UNAVAILABLE",
                "El motor no esta disponible."
            ) from exc

        finally:
            slot.lock.release()

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
        "message": "Datos inválidos: verifica el FEN y el nivel de dificultad (entero entre 1 y 20).",
    }})


@app.get("/health")
def health(request: Request):
    if not request.app.state.engine.healthy():
        raise BotError(503, "ENGINE_UNAVAILABLE", "El motor no está disponible.")
    return {"status": "ok"}

@app.post("/internal/engine/best-move", response_model=InternalMoveResponse)
def internal_best_move(data: InternalMoveRequest, request: Request):
    result = request.app.state.engine.best_move(
        parse_position(data.fen),
        data.botLevel
    )

    return InternalMoveResponse(
        uci=result.uci,
        san=result.san,
        evaluation=InternalEvaluation(
            **result.evaluation.model_dump()
        )
    )

@app.post("/engine/best-move", response_model=MoveResponse)
def best_move(data: MoveRequest, request: Request):
    return request.app.state.engine.best_move(parse_position(data.fen), data.level)


@app.post("/best-move", response_model=LegacyMoveResponse)
def legacy_best_move(data: MoveRequest, request: Request):
    """Compatibilidad con BotcitoClient.java: conserva move sin perder la evaluación."""
    result = best_move(data, request)
    return LegacyMoveResponse(**result.model_dump(), move=result.uci)
