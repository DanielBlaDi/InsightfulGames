"""Frames WebSocket de Single Player atendidos por el gateway.

El gateway mantiene abierto el WebSocket hacia el hub (así la presencia y las sesiones del hub siguen
correctas) pero ya no le reenvía las acciones del cliente: las ejecuta él contra Game Logic y Botcito y
responde él mismo al cliente cuando la acción no se acepta. Todo lo que cambia la partida llega al
cliente por el hub, vía `publish`.

Las acciones de una conexión se procesan en orden por un único trabajador que NO se cancela si el cliente
se desconecta: una jugada que Game Logic ya aceptó debe publicarse y el turno del bot terminar.
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from . import single_player
from .context import Ctx
from .errors import GatewayError

logger = logging.getLogger("gateway.web")

# 400, 409 y 422 son acciones no aceptadas (move_rejected); el resto (404, 5xx) son fallos ajenos a la
# jugada que no cambian la partida (error)
REJECTION_STATUSES = (400, 409, 422)

Send = Callable[[dict[str, Any]], Awaitable[None]]


def rejected(code: str, message: str) -> dict[str, str]:
    return {"type": "move_rejected", "code": code, "message": message}


def error(code: str, message: str) -> dict[str, str]:
    return {"type": "error", "code": code, "message": message}


def message_for(exc: GatewayError) -> dict[str, str]:
    """move_rejected si la acción no se aceptó; error si el fallo es ajeno a la jugada."""
    if exc.status in REJECTION_STATUSES:
        return rejected(exc.code, exc.message)
    return error(exc.code, exc.message)


async def handle_frame(ctx: Ctx, user_id: str, game_id: str, text: str, send: Send) -> None:
    """Una acción del cliente. Nunca lanza: todo error se le responde al cliente."""
    try:
        message = json.loads(text)
    except ValueError:
        message = None
    if not isinstance(message, dict):
        await send(rejected("VALIDATION_ERROR", "El mensaje no es un JSON válido"))
        return
    kind = message.get("type")
    if kind is None:
        await send(rejected("VALIDATION_ERROR", "Falta el campo type"))
        return

    try:
        if kind == "move":
            await single_player.handle_move(ctx, user_id, game_id, message.get("uci"), message.get("expectedVersion"))
        elif kind == "resign":
            await single_player.resign_side(ctx, user_id, game_id, message.get("side"))
        else:
            await send(rejected("VALIDATION_ERROR", f"Tipo de mensaje desconocido: {kind}"))
    except GatewayError as exc:
        await send(message_for(exc))
    except Exception:  # noqa: BLE001
        logger.exception("Error inesperado en la partida %s", game_id)
        await send(error("INTERNAL_ERROR", "Error interno del servidor"))


async def frame_worker(queue: "asyncio.Queue[str | None]", handler: Callable[[str], Awaitable[None]]) -> None:
    """Procesa los frames de una conexión en orden hasta recibir el centinela (None)."""
    while True:
        text = await queue.get()
        if text is None:
            return
        await handler(text)


def start_frame_worker(ctx: Ctx, user_id: str, game_id: str, send: Send) -> "tuple[asyncio.Queue[str | None], asyncio.Task]":
    """Cola de frames y su trabajador, registrado en ctx.tasks para que sobreviva a la desconexión."""
    queue: "asyncio.Queue[str | None]" = asyncio.Queue()

    async def handler(text: str) -> None:
        await handle_frame(ctx, user_id, game_id, text, send)

    return queue, ctx.tasks.spawn(frame_worker(queue, handler))
