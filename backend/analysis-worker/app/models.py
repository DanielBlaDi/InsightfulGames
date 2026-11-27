"""Modelos internos del Analysis Worker.

Los nombres de los documentos y de los eventos son camelCase, igual que el
contrato, para no traducir datos entre componentes.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from app.errors import MessageValidationError

EVENT_TYPE = "tutor.analysis.requested"


@dataclass(frozen=True)
class AnalysisRequestEvent:
    event_id: str
    analysis_id: str
    game_id: str
    depth: int


@dataclass(frozen=True)
class GameMove:
    ply: int
    color: str  # "white" o "black"
    uci: str
    san: str


@dataclass(frozen=True)
class GameInput:
    game_id: str
    initial_fen: str
    moves: tuple[GameMove, ...]
    # N+1 posiciones: la inicial y la que queda tras cada jugada.
    positions: tuple[str, ...]
    # True si la posición es jaque mate (no una posición con mate forzado).
    terminal_mate: tuple[bool, ...]


@dataclass(frozen=True)
class Evaluation:
    value: int  # centipeones desde blancas
    is_mate: bool
    best_uci: str | None
    best_san: str | None
    depth: int | None = None


def _uuid_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MessageValidationError(f"El campo {field_name} es obligatorio.")
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError, TypeError) as exc:
        raise MessageValidationError(
            f"El campo {field_name} debe ser un UUID válido."
        ) from exc


def parse_event(body: bytes, maximum_depth: int) -> AnalysisRequestEvent:
    """Valida el mensaje ``tutor.analysis.requested``.

    Un mensaje inválido se envía directamente a ``.dlq`` (sección 19.4).
    """
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MessageValidationError("El mensaje no está codificado en UTF-8.") from exc

    try:
        payload = json.loads(decoded)
    except (ValueError, TypeError) as exc:
        raise MessageValidationError("El mensaje no es JSON válido.") from exc

    if not isinstance(payload, Mapping):
        raise MessageValidationError("El mensaje debe ser un objeto JSON.")

    event_type = payload.get("eventType")
    if event_type != EVENT_TYPE:
        raise MessageValidationError(
            f"El campo eventType debe ser {EVENT_TYPE}."
        )

    event_id = _uuid_text(payload.get("eventId"), "eventId")
    analysis_id = _uuid_text(payload.get("analysisId"), "analysisId")
    game_id = _uuid_text(payload.get("gameId"), "gameId")

    depth = payload.get("depth")
    if isinstance(depth, bool) or not isinstance(depth, int):
        raise MessageValidationError("El campo depth debe ser un entero.")
    if depth < 1 or depth > maximum_depth:
        raise MessageValidationError(
            f"El campo depth debe estar entre 1 y {maximum_depth}."
        )

    return AnalysisRequestEvent(
        event_id=event_id,
        analysis_id=analysis_id,
        game_id=game_id,
        depth=depth,
    )
