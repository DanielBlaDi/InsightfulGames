"""Lectura de partidas en Game Logic (GET /internal/logic/games/{id})."""

from typing import Any, Mapping

import httpx

from . import upstream
from .errors import FlowError, GatewayError


async def get_game(
    client: httpx.AsyncClient,
    upstreams: Mapping[str, str],
    game_id: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    """GameState de la partida.

    404 -> FlowError 404 GAME_NOT_FOUND. Un fallo de red, de tiempo, otro estado distinto de 200 o
    un cuerpo que no es un objeto JSON -> FlowError 503 SERVICES_UNAVAILABLE.
    """
    try:
        response = await upstream.call(
            client, upstreams["logic"], "logic", "GET", f"/games/{game_id}", timeout=timeout
        )
    except GatewayError:
        raise FlowError(503, "SERVICES_UNAVAILABLE", "Game Logic no está disponible en este momento.")

    if response.status_code == 404:
        raise FlowError(404, "GAME_NOT_FOUND", "La partida no existe.")
    if response.status_code != 200:
        raise FlowError(503, "SERVICES_UNAVAILABLE", "Game Logic no pudo entregar la partida.")
    try:
        game = response.json()
    except ValueError:
        game = None
    if not isinstance(game, dict):
        raise FlowError(503, "SERVICES_UNAVAILABLE", "Game Logic devolvió una respuesta inválida.")
    return game
