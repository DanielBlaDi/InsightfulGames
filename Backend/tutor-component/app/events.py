"""Publicación de ``tutor.analysis.requested`` en RabbitMQ (contrato, sección 17).

La publicación nunca hace fallar la petición del usuario: si el broker no está,
el análisis queda en ``pending`` y el Analysis Worker lo recoge por polling
(sección 14). Ese es el riesgo aceptado de la sección 24.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import aio_pika

from app.config import ANALYSIS_REQUESTED_ROUTING_KEY, TUTOR_EVENTS_EXCHANGE
from app.timeutils import to_iso, utcnow

LOGGER = logging.getLogger("tutor.events")

EVENT_TYPE = "tutor.analysis.requested"


class EventPublisher:
    """Publica eventos del Tutor en el exchange ``tutor.events`` (topic, durable).

    El Tutor declara el exchange, no la cola: ``analysis-worker.requested`` es
    del Analysis Worker. Si el worker aún no está arriba, el mensaje se pierde
    en el exchange y el polling del worker lo recupera.
    """

    def __init__(
        self,
        url: str,
        exchange: str = TUTOR_EVENTS_EXCHANGE,
        routing_key: str = ANALYSIS_REQUESTED_ROUTING_KEY,
        timeout: float = 5.0,
    ):
        self._url = url
        self._exchange_name = exchange
        self._routing_key = routing_key
        self._timeout = timeout
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return (
            self._connection is not None
            and not self._connection.is_closed
            and self._exchange is not None
        )

    async def start(self) -> bool:
        """Intenta conectar al arrancar. Un fallo no impide levantar el servicio."""
        async with self._lock:
            if self.connected:
                return True
            return await self._connect_locked()

    async def close(self) -> None:
        async with self._lock:
            await self._discard_connection()

    async def _connect_locked(self) -> bool:
        try:
            connection = await aio_pika.connect_robust(
                self._url, timeout=self._timeout
            )
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                self._exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
        except Exception:
            LOGGER.exception(
                "No se pudo conectar a RabbitMQ (%s). El Tutor seguirá aceptando "
                "análisis, que quedarán en pending hasta que el worker los recoja.",
                self._url,
            )
            await self._discard_connection()
            return False

        self._connection = connection
        self._exchange = exchange
        LOGGER.info(
            "Conectado a RabbitMQ; exchange %s durable y listo",
            self._exchange_name,
        )
        return True

    async def _discard_connection(self) -> None:
        connection = self._connection
        self._connection = None
        self._exchange = None
        if connection is not None:
            try:
                await connection.close()
            except Exception:  # pragma: no cover - cierre best effort
                LOGGER.debug("Error cerrando la conexión de RabbitMQ", exc_info=True)

    async def _ensure_connection(self) -> bool:
        if self.connected:
            return True
        async with self._lock:
            if self.connected:
                return True
            return await self._connect_locked()

    async def publish_analysis_requested(self, analysis: dict[str, Any]) -> bool:
        """Publica el evento del análisis. Devuelve False si no se pudo publicar."""
        if not await self._ensure_connection():
            return False

        payload = build_event_payload(analysis)
        try:
            message = aio_pika.Message(
                body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
                content_encoding="utf-8",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=payload["eventId"],
                timestamp=utcnow(),
            )
            exchange = self._exchange
            if exchange is None:
                raise RuntimeError("El exchange no está disponible")
            await exchange.publish(
                message,
                routing_key=self._routing_key,
                timeout=self._timeout,
            )
        except Exception:
            LOGGER.exception(
                "No se pudo publicar %s para el análisis %s; queda en pending",
                EVENT_TYPE,
                analysis.get("analysisId"),
            )
            await self._discard_connection()
            return False

        LOGGER.info(
            "Publicado %s analysisId=%s depth=%s",
            EVENT_TYPE,
            payload["analysisId"],
            payload["depth"],
        )
        return True


def build_event_payload(analysis: dict[str, Any]) -> dict[str, Any]:
    """Evento ``tutor.analysis.requested`` con los campos de la sección 17."""
    return {
        "eventId": str(uuid.uuid4()),
        "eventType": EVENT_TYPE,
        "occurredAt": to_iso(utcnow()),
        "analysisId": analysis["analysisId"],
        "gameId": analysis["gameId"],
        "requestedBy": analysis["requestedBy"],
        "language": analysis["language"],
        "detailLevel": analysis["detailLevel"],
        "depth": analysis["depth"],
    }
