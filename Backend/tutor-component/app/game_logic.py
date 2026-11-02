"""Lectura de partidas desde Game Logic por el gateway interno.

El contrato (sección 11) dice que Game Logic guarda ``visibility`` y
``participants`` pero no decide quién puede ver la partida: esa validación la
hace el Tutor. Por eso aquí solo se obtiene el GameState y la regla de
visibilidad se aplica en :func:`is_visible`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.errors import ApiError

LOGGER = logging.getLogger("tutor.game_logic")


class GameLogicClient:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def get_game(self, game_id: str) -> dict[str, Any]:
        try:
            response = await self._client.get(f"/internal/logic/games/{game_id}")
        except httpx.HTTPError as exc:
            LOGGER.error("Game Logic no respondió: %s", exc)
            raise ApiError(
                503,
                "SERVICES_UNAVAILABLE",
                "Game Logic no está disponible en este momento.",
            ) from exc

        if response.status_code == 404:
            raise ApiError(
                404, "GAME_NOT_FOUND", "La partida no existe."
            )

        if response.status_code != 200:
            LOGGER.error(
                "Game Logic respondió %s al consultar la partida %s",
                response.status_code,
                game_id,
            )
            raise ApiError(
                503,
                "SERVICES_UNAVAILABLE",
                "Game Logic no pudo entregar la partida.",
            )

        try:
            game = response.json()
        except ValueError as exc:
            LOGGER.error("Game Logic devolvió una respuesta que no es JSON")
            raise ApiError(
                503,
                "SERVICES_UNAVAILABLE",
                "Game Logic devolvió una respuesta inválida.",
            ) from exc

        if not isinstance(game, dict):
            raise ApiError(
                503,
                "SERVICES_UNAVAILABLE",
                "Game Logic devolvió una respuesta inválida.",
            )
        return game


def participant_ids(game: dict[str, Any]) -> list[str]:
    """userId de cada participante, sin repetir (en local el creador juega ambos colores)."""
    participants = game.get("participants")
    if not isinstance(participants, list):
        return []
    ids: list[str] = []
    for participant in participants:
        if not isinstance(participant, dict):
            continue
        user_id = participant.get("userId")
        if isinstance(user_id, str) and user_id and user_id not in ids:
            ids.append(user_id)
    return ids


def is_visible(game: dict[str, Any], user_id: str) -> bool:
    """Regla de visibilidad de la sección 13.

    - ``shared``: cualquiera que pueda ver la partida puede pedir y leer el análisis.
    - ``private``: solo los participantes.
    - Sin ``visibility`` (Game Logic anterior a v9): se usa ``participants`` y,
      como último recurso, el creador. Así el Tutor sigue funcionando mientras
      el otro equipo despliega el GameState de v9.
    """
    visibility = game.get("visibility")
    if visibility == "shared":
        return True
    if visibility not in (None, "private"):
        return False

    ids = participant_ids(game)
    if ids:
        return user_id in ids

    creator = game.get("userId") or game.get("createdBy")
    return isinstance(creator, str) and creator == user_id


def visibility_snapshot(game: dict[str, Any]) -> str:
    """Visibilidad guardada en el análisis en el momento de crearlo."""
    return "shared" if game.get("visibility") == "shared" else "private"
