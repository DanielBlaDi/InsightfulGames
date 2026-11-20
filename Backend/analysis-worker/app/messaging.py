"""Decisión de confirmación de un mensaje de análisis (sección 19.4)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from app.config import MAX_BROKER_RETRIES
from app.errors import MessageValidationError
from app.models import parse_event

LOGGER = logging.getLogger("analysis-worker.messaging")

ACTION_ACK = "ack"
ACTION_RETRY = "retry"
ACTION_DLQ = "dlq"
ACTION_REQUEUE = "requeue"


@dataclass(frozen=True)
class HandlerAction:
    kind: str
    retry_count: int | None = None


def _retry_count(headers: Mapping[str, Any] | None) -> int:
    if not headers:
        return 0
    raw = headers.get("x-retry-count", 0)
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("ascii")
        except UnicodeDecodeError:
            return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


class MessageHandler:
    """Convierte un mensaje en una acción para el broker."""

    def __init__(
        self,
        processor: Any,
        *,
        maximum_depth: int,
        max_broker_retries: int = MAX_BROKER_RETRIES,
    ):
        self._processor = processor
        self._maximum_depth = maximum_depth
        self._max_broker_retries = max_broker_retries

    async def handle(
        self, body: bytes, headers: Mapping[str, Any] | None = None
    ) -> HandlerAction:
        try:
            event = parse_event(body, self._maximum_depth)
        except MessageValidationError as exc:
            LOGGER.warning("Mensaje inválido enviado a .dlq: %s", exc)
            return HandlerAction(ACTION_DLQ)

        try:
            await self._processor.process(event.analysis_id)
        except Exception:
            # Fallo de infraestructura (Mongo, broker, error inesperado). El
            # worker no debe confirmar el mensaje: se reintenta por el broker
            # o se deja para la recuperación por polling.
            LOGGER.exception(
                "Análisis %s: fallo de infraestructura procesando el mensaje",
                event.analysis_id,
            )
            current = _retry_count(headers)
            if current >= self._max_broker_retries:
                LOGGER.error(
                    "Análisis %s: agotados los reintentos del broker; va a .dlq",
                    event.analysis_id,
                )
                return HandlerAction(ACTION_DLQ)
            return HandlerAction(ACTION_RETRY, retry_count=current + 1)

        # completed, failed, skipped, discarded y lease_lost se confirman: un
        # análisis failed no se reintenta por el broker (sección 16.4.3).
        return HandlerAction(ACTION_ACK)
