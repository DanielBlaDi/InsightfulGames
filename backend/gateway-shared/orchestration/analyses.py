"""Flows del Tutor (contrato, sección 16.4). El gateway orquesta; el Tutor no llama a nadie.

- create: Game Logic (leer la partida) -> visibilidad -> Tutor POST con un snapshot de la partida.
- read:   Tutor game-ref -> Game Logic -> visibilidad -> Tutor GET (estado o resultado).
- erase_user: Tutor game-ids -> Game Logic (visibilidad actual de cada partida) -> Tutor erase.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Mapping

import httpx

from . import logic, upstream
from .errors import FlowError, GatewayError, deletion_unavailable
from .visibility import is_visible, participant_ids

logger = logging.getLogger("gateway.orchestration")

INVALID_BODY = "La solicitud no cumple el formato esperado."
NOT_VISIBLE = "La partida no existe o no es visible para el usuario."
ANALYSIS_NOT_VISIBLE = "El análisis no existe o no es visible para el usuario."

# Campos del cliente que se reenvían al Tutor; nada más (en particular, nunca `game`).
FORWARDED_FIELDS = ("language", "detailLevel", "depth")
# Consultas simultáneas a Game Logic durante el borrado de cuenta
ERASE_CONCURRENCY = 8


def _snapshot(game: dict[str, Any]) -> dict[str, Any]:
    """Lo mínimo que el Tutor necesita de la partida, armado campo a campo (nunca se copia el estado)."""
    status = game.get("status")
    end_reason = game.get("endReason")
    moves = game.get("moves")
    return {
        "status": status if isinstance(status, str) else None,
        "endReason": end_reason if isinstance(end_reason, str) else None,
        "moveCount": len(moves) if isinstance(moves, list) else 0,
        "participantIds": participant_ids(game),
    }


def _game_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FlowError(400, "VALIDATION_ERROR", "El campo gameId es obligatorio.")
    try:
        game_id = uuid.UUID(value.strip())
    except ValueError:
        raise FlowError(400, "VALIDATION_ERROR", "El campo gameId debe ser un UUID v4 válido.")
    if game_id.version != 4:
        raise FlowError(400, "VALIDATION_ERROR", "El campo gameId debe ser un UUID v4 válido.")
    return str(game_id)


async def _tutor(
    client: httpx.AsyncClient,
    upstreams: Mapping[str, str],
    method: str,
    path: str,
    *,
    timeout: float,
    user_id: str | None = None,
    json: Any = None,
) -> httpx.Response:
    return await upstream.call(
        client, upstreams["tutor"], "tutor", method, path,
        user_id=user_id, json=json, timeout=timeout,
    )


async def create(
    client: httpx.AsyncClient,
    upstreams: Mapping[str, str],
    user_id: str,
    raw_body: bytes,
    *,
    timeout: float,
) -> httpx.Response:
    """POST /tutor/analyses. Devuelve la respuesta del Tutor (para traducirla con relay)."""
    try:
        body = json.loads(raw_body or b"null")
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise FlowError(400, "VALIDATION_ERROR", INVALID_BODY)

    game_id = _game_id(body.get("gameId"))
    game = await logic.get_game(client, upstreams, game_id, timeout=timeout)
    if not is_visible(game, user_id):
        # El contrato no distingue "no existe" de "no visible" (sección 16.4)
        raise FlowError(404, "GAME_NOT_FOUND", NOT_VISIBLE)

    forwarded: dict[str, Any] = {"gameId": game_id, "game": _snapshot(game)}
    forwarded.update({k: body[k] for k in FORWARDED_FIELDS if k in body})
    return await _tutor(
        client, upstreams, "POST", "/analyses", timeout=timeout, user_id=user_id, json=forwarded
    )


async def read(
    client: httpx.AsyncClient,
    upstreams: Mapping[str, str],
    user_id: str,
    analysis_id: str,
    *,
    suffix: str = "",
    timeout: float,
) -> httpx.Response:
    """GET /tutor/analyses/{id}[/result]. La visibilidad se recalcula en cada lectura."""
    ref = await _tutor(client, upstreams, "GET", f"/analyses/{analysis_id}/game-ref", timeout=timeout)
    if ref.status_code != 200:
        return ref  # ANALYSIS_NOT_FOUND u otro error del Tutor: se traduce con relay
    try:
        game_id = ref.json().get("gameId")
    except (ValueError, AttributeError):
        game_id = None
    if not isinstance(game_id, str) or not game_id:
        raise FlowError(502, "UPSTREAM_ERROR", "Respuesta inesperada del servicio")

    try:
        game = await logic.get_game(client, upstreams, game_id, timeout=timeout)
    except FlowError as exc:
        if exc.code == "GAME_NOT_FOUND":
            # La partida desapareció: para el usuario el análisis tampoco existe (sección 16.4.2)
            raise FlowError(404, "ANALYSIS_NOT_FOUND", ANALYSIS_NOT_VISIBLE)
        raise
    if not is_visible(game, user_id):
        raise FlowError(404, "ANALYSIS_NOT_FOUND", ANALYSIS_NOT_VISIBLE)

    return await _tutor(client, upstreams, "GET", f"/analyses/{analysis_id}{suffix}", timeout=timeout)


async def erase_user(
    client: httpx.AsyncClient,
    upstreams: Mapping[str, str],
    user_id: str,
    *,
    timeout: float,
) -> None:
    """Paso del Tutor en el borrado de cuenta (sección 16.4.4).

    Primero se resuelve la visibilidad actual de todas las partidas y solo después se muta: si Game
    Logic o el Tutor fallan antes del erase, no se toca ningún análisis. Solo las partidas shared
    se conservan; una partida inexistente (404), privada o con cualquier valor inesperado se borra.
    Lanza FlowError 503 nombrando al servicio que falló.
    """
    try:
        listing = await _tutor(client, upstreams, "GET", f"/users/{user_id}/game-ids", timeout=timeout)
    except GatewayError:
        raise deletion_unavailable("Tutor")
    try:
        game_ids = listing.json().get("gameIds") if listing.status_code == 200 else None
    except (ValueError, AttributeError):
        game_ids = None
    if not isinstance(game_ids, list) or not all(isinstance(g, str) for g in game_ids):
        logger.warning("Borrado de cuenta: el Tutor respondió %s al listar partidas", listing.status_code)
        raise deletion_unavailable("Tutor")

    gate = asyncio.Semaphore(ERASE_CONCURRENCY)

    async def keep(game_id: str) -> bool:
        async with gate:
            try:
                game = await logic.get_game(client, upstreams, game_id, timeout=timeout)
            except FlowError as exc:
                if exc.code == "GAME_NOT_FOUND":
                    return False  # partida inexistente: se borran sus análisis
                raise deletion_unavailable("Game Logic")
        return game.get("visibility") == "shared"

    decisions = await asyncio.gather(*(keep(g) for g in game_ids))
    keep_game_ids = [g for g, kept in zip(game_ids, decisions) if kept]

    try:
        erased = await _tutor(
            client, upstreams, "POST", f"/users/{user_id}/erase",
            timeout=timeout, json={"keepGameIds": keep_game_ids},
        )
    except GatewayError:
        raise deletion_unavailable("Tutor")
    if erased.status_code != 204:
        logger.warning("Borrado de cuenta: el Tutor respondió %s al borrar", erased.status_code)
        raise deletion_unavailable("Tutor")
