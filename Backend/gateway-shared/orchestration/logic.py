"""Llamadas a Game Logic (/internal/logic/games/*)."""

from typing import Any, Mapping

import httpx

from . import upstream
from .errors import FlowError, GatewayError, payload_of, upstream_flow_error


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


# --- Operaciones del juego en vivo (single-player y multiplayer) ---------------------------------
# A diferencia de get_game (que usa el Tutor), estas conservan el estado y el código de los errores de
# Game Logic: los 4xx pasan tal cual y los 5xx se reducen al catálogo (ENGINE_*, SERVICES_UNAVAILABLE).


async def _call(
    client: httpx.AsyncClient,
    upstreams: Mapping[str, str],
    method: str,
    path: str,
    *,
    timeout: float,
    json: Any = None,
) -> dict[str, Any]:
    response = await upstream.call(
        client, upstreams["logic"], "logic", method, path, json=json, timeout=timeout
    )
    if not response.is_success:
        raise upstream_flow_error(response, "Game Logic")
    state = payload_of(response)
    if not isinstance(state, dict):
        raise FlowError(503, "SERVICES_UNAVAILABLE", "Game Logic devolvió una respuesta vacía")
    return state


async def fetch_game(client, upstreams, game_id: str, *, timeout: float) -> dict[str, Any]:
    return await _call(client, upstreams, "GET", f"/games/{game_id}", timeout=timeout)


async def create_game(client, upstreams, body: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    return await _call(client, upstreams, "POST", "/games", timeout=timeout, json=body)


async def move(client, upstreams, game_id: str, uci: str, expected_version: int, *, timeout: float):
    return await _call(
        client, upstreams, "POST", f"/games/{game_id}/moves", timeout=timeout,
        json={"uci": uci, "expectedVersion": expected_version},
    )


async def resign(client, upstreams, game_id: str, side: str | None, *, timeout: float):
    return await _call(
        client, upstreams, "POST", f"/games/{game_id}/resign", timeout=timeout, json={"side": side}
    )


async def set_visibility(
    client, upstreams, game_id: str, visibility: str, expected_version: int, *, timeout: float
):
    return await _call(
        client, upstreams, "PATCH", f"/games/{game_id}/visibility", timeout=timeout,
        json={"visibility": visibility, "expectedVersion": expected_version},
    )
