"""Cliente y topología de RabbitMQ del Analysis Worker (secciones 17 y 19)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

import aio_pika

from app.config import (
    ANALYSIS_REQUESTED_ROUTING_KEY,
    DLQ,
    MAIN_QUEUE,
    RETRY_EXCHANGE,
    RETRY_TTL_MS,
    TUTOR_EVENTS_EXCHANGE,
    WAIT_QUEUE,
)
from app.messaging import (
    ACTION_ACK,
    ACTION_DLQ,
    ACTION_REQUEUE,
    ACTION_RETRY,
    HandlerAction,
)

LOGGER = logging.getLogger("analysis-worker.broker")

Handler = Callable[[bytes, dict[str, Any] | None], Awaitable[HandlerAction]]


class RabbitMQBroker:
    def __init__(self, url: str, timeout: float = 5.0):
        self._url = url
        self._timeout = timeout
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._queue: aio_pika.abc.AbstractQueue | None = None
        self._retry_exchange: aio_pika.abc.AbstractExchange | None = None

    @property
    def connected(self) -> bool:
        return (
            self._connection is not None
            and not self._connection.is_closed
            and self._channel is not None
            and not self._channel.is_closed
        )

    async def start(self) -> None:
        """Conecta y declara exchange, cola principal, .wait y .dlq."""
        if self.connected:
            return
        await self.close()

        self._connection = await aio_pika.connect_robust(
            self._url, timeout=self._timeout
        )
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=1)

        tutor_exchange = await channel.declare_exchange(
            TUTOR_EVENTS_EXCHANGE,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        retry_exchange = await channel.declare_exchange(
            RETRY_EXCHANGE,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

        queue = await channel.declare_queue(MAIN_QUEUE, durable=True)
        wait_queue = await channel.declare_queue(
            WAIT_QUEUE,
            durable=True,
            arguments={
                "x-message-ttl": RETRY_TTL_MS,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": MAIN_QUEUE,
            },
        )
        await channel.declare_queue(DLQ, durable=True)

        await queue.bind(
            tutor_exchange, routing_key=ANALYSIS_REQUESTED_ROUTING_KEY
        )
        await wait_queue.bind(retry_exchange, routing_key=MAIN_QUEUE)

        self._channel = channel
        self._queue = queue
        self._retry_exchange = retry_exchange
        LOGGER.info(
            "RabbitMQ listo: %s -> %s (prefetch=1)", TUTOR_EVENTS_EXCHANGE, MAIN_QUEUE
        )

    async def close(self) -> None:
        connection = self._connection
        self._connection = None
        self._channel = None
        self._queue = None
        self._retry_exchange = None
        if connection is not None:
            try:
                await connection.close()
            except Exception:  # pragma: no cover - cierre best effort
                LOGGER.debug("Error cerrando RabbitMQ", exc_info=True)

    async def consume(self, handler: Handler) -> None:
        """Consume de uno en uno hasta que la conexión se cierre."""
        queue = self._queue
        if queue is None:
            raise RuntimeError("La cola no está declarada")

        async with queue.iterator() as iterator:
            async for message in iterator:
                await self._handle(message, handler)

    async def _handle(
        self, message: aio_pika.abc.AbstractIncomingMessage, handler: Handler
    ) -> None:
        try:
            action = await handler(message.body, message.headers)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Error inesperado manejando un mensaje")
            action = HandlerAction(ACTION_REQUEUE)

        try:
            if action.kind == ACTION_ACK:
                await message.ack()
            elif action.kind == ACTION_RETRY:
                await self.publish_retry(
                    message.body,
                    message.headers,
                    action.retry_count or 1,
                    message_id=message.message_id,
                )
                await message.ack()
            elif action.kind == ACTION_DLQ:
                await self.publish_dlq(
                    message.body,
                    message.headers,
                    message_id=message.message_id,
                )
                await message.ack()
            else:
                await message.nack(requeue=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Si el reenvío falla, se rechaza con requeue. RabbitMQ volverá a
            # entregar el mensaje y el lease/polling evita duplicar trabajo.
            LOGGER.exception("No se pudo confirmar o reenviar el mensaje")
            try:
                await message.nack(requeue=True)
            except Exception:
                LOGGER.exception("Tampoco se pudo rechazar el mensaje con requeue")

    async def publish_retry(
        self,
        body: bytes,
        headers: dict[str, Any] | None,
        retry_count: int,
        *,
        message_id: str | None = None,
    ) -> None:
        exchange = self._retry_exchange
        if exchange is None:
            raise RuntimeError("El exchange de reintentos no está disponible")

        new_headers = dict(headers or {})
        new_headers["x-retry-count"] = retry_count
        message = aio_pika.Message(
            body=body,
            headers=new_headers,
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=message_id,
        )
        await exchange.publish(message, routing_key=MAIN_QUEUE)

    async def publish_dlq(
        self,
        body: bytes,
        headers: dict[str, Any] | None,
        *,
        message_id: str | None = None,
    ) -> None:
        channel = self._channel
        if channel is None:
            raise RuntimeError("El canal de RabbitMQ no está disponible")

        message = aio_pika.Message(
            body=body,
            headers=dict(headers or {}),
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=message_id,
        )
        await channel.default_exchange.publish(message, routing_key=DLQ)
