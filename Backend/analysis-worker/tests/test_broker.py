"""Pruebas de la topología RabbitMQ del worker (contrato, secciones 17 y 19)."""

from __future__ import annotations

import pytest
from aio_pika import ExchangeType

from app.broker import RabbitMQBroker
from app.config import (
    ANALYSIS_REQUESTED_ROUTING_KEY,
    DLQ,
    MAIN_QUEUE,
    RETRY_EXCHANGE,
    RETRY_TTL_MS,
    TUTOR_EVENTS_EXCHANGE,
    WAIT_QUEUE,
)


class FakeExchange:
    def __init__(self, name: str):
        self.name = name
        self.published: list[tuple[object, str]] = []

    async def publish(self, message, routing_key: str) -> None:
        self.published.append((message, routing_key))


class FakeQueue:
    def __init__(self, name: str):
        self.name = name
        self.bindings: list[tuple[str, str]] = []

    async def bind(self, exchange, routing_key: str) -> None:
        self.bindings.append((exchange.name, routing_key))


class FakeChannel:
    def __init__(self):
        self.is_closed = False
        self.prefetch_count: int | None = None
        self.exchanges: list[tuple[str, object, bool]] = []
        self.queues: list[tuple[str, bool, dict | None]] = []
        self.exchange_objects: dict[str, FakeExchange] = {}
        self.queue_objects: dict[str, FakeQueue] = {}
        self.default_exchange = FakeExchange("<default>")

    async def set_qos(self, prefetch_count: int) -> None:
        self.prefetch_count = prefetch_count

    async def declare_exchange(self, name: str, exchange_type, durable: bool = True):
        self.exchanges.append((name, exchange_type, durable))
        exchange = FakeExchange(name)
        self.exchange_objects[name] = exchange
        return exchange

    async def declare_queue(
        self, name: str, durable: bool = True, arguments: dict | None = None
    ):
        self.queues.append((name, durable, arguments))
        queue = FakeQueue(name)
        self.queue_objects[name] = queue
        return queue


class FakeConnection:
    def __init__(self, channel: FakeChannel):
        self.channel_obj = channel
        self.is_closed = False
        self.closed = 0

    async def channel(self) -> FakeChannel:
        return self.channel_obj

    async def close(self) -> None:
        self.closed += 1
        self.is_closed = True


async def test_topology_matches_the_contract(monkeypatch):
    channel = FakeChannel()
    connection = FakeConnection(channel)
    connects = 0

    async def connect_robust(url, timeout):
        nonlocal connects
        connects += 1
        return connection

    monkeypatch.setattr("app.broker.aio_pika.connect_robust", connect_robust)
    broker = RabbitMQBroker("amqp://unused", timeout=1.0)

    await broker.start()

    assert connects == 1
    assert broker.connected is True
    assert channel.prefetch_count == 1
    assert (TUTOR_EVENTS_EXCHANGE, ExchangeType.TOPIC, True) in channel.exchanges
    assert (RETRY_EXCHANGE, ExchangeType.DIRECT, True) in channel.exchanges

    queues = {name: (durable, arguments) for name, durable, arguments in channel.queues}
    assert queues[MAIN_QUEUE] == (True, None)
    assert queues[DLQ] == (True, None)
    assert queues[WAIT_QUEUE][0] is True
    assert queues[WAIT_QUEUE][1] == {
        "x-message-ttl": RETRY_TTL_MS,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": MAIN_QUEUE,
    }

    main_queue = channel.queue_objects[MAIN_QUEUE]
    assert (TUTOR_EVENTS_EXCHANGE, ANALYSIS_REQUESTED_ROUTING_KEY) in main_queue.bindings
    wait_queue = channel.queue_objects[WAIT_QUEUE]
    assert (RETRY_EXCHANGE, MAIN_QUEUE) in wait_queue.bindings

    # Un segundo start no vuelve a conectar mientras la conexión está sana.
    await broker.start()
    assert connects == 1

    await broker.close()
    assert connection.closed == 1
    assert broker.connected is False


async def test_retry_and_dlq_publication(monkeypatch):
    channel = FakeChannel()
    connection = FakeConnection(channel)

    async def connect_robust(url, timeout):
        return connection

    monkeypatch.setattr("app.broker.aio_pika.connect_robust", connect_robust)
    broker = RabbitMQBroker("amqp://unused")
    await broker.start()

    await broker.publish_retry(
        b'{"eventType": "tutor.analysis.requested"}',
        {"x-retry-count": 1, "otro": "valor"},
        2,
        message_id="message-1",
    )
    retry_exchange = channel.exchange_objects[RETRY_EXCHANGE]
    message, routing_key = retry_exchange.published[0]
    assert routing_key == MAIN_QUEUE
    assert message.headers["x-retry-count"] == 2
    assert message.headers["otro"] == "valor"
    assert message.message_id == "message-1"

    await broker.publish_dlq(b"{}", {"x-retry-count": 5}, message_id="message-2")
    message, routing_key = channel.default_exchange.published[0]
    assert routing_key == DLQ
    assert message.message_id == "message-2"

    await broker.close()


async def test_publish_without_start_fails():
    broker = RabbitMQBroker("amqp://unused")

    with pytest.raises(RuntimeError):
        await broker.publish_retry(b"{}", None, 1)

    with pytest.raises(RuntimeError):
        await broker.publish_dlq(b"{}", None)
