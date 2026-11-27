"""Botcito-juego (POST /internal/engine/best-move)."""

from typing import Any, Mapping

import httpx

from . import upstream
from .errors import FlowError, payload_of, upstream_flow_error


async def best_move(
    client: httpx.AsyncClient,
    upstreams: Mapping[str, str],
    fen: str,
    bot_level: int,
    *,
    timeout: float,
) -> dict[str, Any]:
    """{ uci, san, evaluation }. Los errores del catálogo (ENGINE_BUSY 503, ENGINE_TIMEOUT 504,
    SERVICES_UNAVAILABLE 503...) pasan con su código real; una jugada vacía es 503."""
    response = await upstream.call(
        client, upstreams["engine"], "engine", "POST", "/best-move",
        json={"fen": fen, "botLevel": bot_level}, timeout=timeout,
    )
    if not response.is_success:
        raise upstream_flow_error(response, "Botcito")
    move = payload_of(response)
    if not isinstance(move, dict) or not isinstance(move.get("uci"), str) or not move["uci"].strip():
        raise FlowError(503, "SERVICES_UNAVAILABLE", "Botcito devolvió una jugada vacía")
    return move
