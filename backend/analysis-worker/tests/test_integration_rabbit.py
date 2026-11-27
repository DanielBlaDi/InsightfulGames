"""Pruebas de integración opcionales con RabbitMQ real.

Se omiten salvo que exista ``RABBITMQ_TEST_URL``. Requieren el plugin de
management para verificar la topología por HTTP.

Ejemplo de ejecución:

    $env:RABBITMQ_TEST_URL = "amqp://analysis:analysis@127.0.0.1:5673/"
    $env:RABBITMQ_MANAGEMENT_URL = "http://127.0.0.1:15673"
    python -m pytest -q tests/test_integration_rabbit.py

Las colas son las del contrato, así que debe apuntarse a un broker temporal sin
otros consumidores.
"""

from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import unquote, urlparse

import aio_pika
import httpx
import pytest
import pytest_asyncio

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
from app.messaging import ACTION_RETRY, HandlerAction, MessageHandler

RABBITMQ_TEST_URL = os.getenv("RABBITMQ_TEST_URL")
RABBITMQ_MANAGEMENT_URL = os.getenv(
    "RABBITMQ_MANAGEMENT_URL", "http://127.0.0.1:15672"
)

pytestmark = pytest.mark.skipif(
    not RABBITMQ_TEST_URL,
    reason="Define RABBITMQ_TEST_URL para ejecutar la integración con RabbitMQ real.",
)


def _management_auth() -> tuple[str, str]:
    parsed = urlparse(RABBITMQ_TEST_URL or "")
    return (
        unquote(parsed.username or "guest"),
        unquote(parsed.password or "guest"),
    )


async def _purge(channel) -> None:
    for name in (MAIN_QUEUE, WAIT_QUEUE, DLQ):
        queue = await channel.declare_queue(name, durable=True, passive=True)
        await queue.purge()


async def _queue_messages(channel, queue: str) -> int:
    declared = await channel.declare_queue(queue, durable=True, passive=True)
    return declared.declaration_result.message_count


async def _wait_for_messages(
    channel, queue: str, expected: int, timeout: float = 5.0
) -> int:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    count = await _queue_messages(channel, queue)
    while count != expected and loop.time() < deadline:
        await asyncio.sleep(0.1)
        count = await _queue_messages(channel, queue)
    return count


@pytest_asyncio.fixture
async def rabbit():
    broker = RabbitMQBroker(RABBITMQ_TEST_URL, timeout=10.0)
    await broker.start()
    connection = await aio_pika.connect_robust(RABBITMQ_TEST_URL, timeout=10.0)
    channel = await connection.channel()
    async with httpx.AsyncClient(
        base_url=RABBITMQ_MANAGEMENT_URL,
        auth=_management_auth(),
        timeout=5.0,
    ) as client:
        await _purge(channel)
        try:
            yield broker, channel, client
        finally:
            await _purge(channel)

    await connection.close()
    await broker.close()


def event_body(analysis_id: str) -> bytes:
    return json.dumps(
        {
            "eventId": "00000000-0000-4000-8000-000000000001",
            "eventType": "tutor.analysis.requested",
            "occurredAt": "2026-11-02T12:00:00Z",
            "analysisId": analysis_id,
            "gameId": "00000000-0000-4000-8000-000000000002",
            "requestedBy": "00000000-0000-4000-8000-000000000003",
            "language": "es",
            "detailLevel": "standard",
            "depth": 15,
        }
    ).encode("utf-8")


async def test_topology_matches_the_contract(rabbit):
    _broker, _channel, client = rabbit

    tutor_exchange = await client.get(f"/api/exchanges/%2F/{TUTOR_EVENTS_EXCHANGE}")
    assert tutor_exchange.status_code == 200
    assert tutor_exchange.json()["type"] == "topic"
    assert tutor_exchange.json()["durable"] is True

    retry_exchange = await client.get(f"/api/exchanges/%2F/{RETRY_EXCHANGE}")
    assert retry_exchange.status_code == 200
    assert retry_exchange.json()["type"] == "direct"
    assert retry_exchange.json()["durable"] is True

    main = await client.get(f"/api/queues/%2F/{MAIN_QUEUE}")
    assert main.status_code == 200
    assert main.json()["durable"] is True

    wait = await client.get(f"/api/queues/%2F/{WAIT_QUEUE}")
    assert wait.status_code == 200
    assert wait.json()["durable"] is True
    assert wait.json()["arguments"]["x-message-ttl"] == RETRY_TTL_MS
    assert wait.json()["arguments"]["x-dead-letter-exchange"] == ""
    assert wait.json()["arguments"]["x-dead-letter-routing-key"] == MAIN_QUEUE

    dlq = await client.get(f"/api/queues/%2F/{DLQ}")
    assert dlq.status_code == 200
    assert dlq.json()["durable"] is True

    main_bindings = await client.get(
        f"/api/queues/%2F/{MAIN_QUEUE}/bindings"
    )
    assert main_bindings.status_code == 200
    assert any(
        binding["source"] == TUTOR_EVENTS_EXCHANGE
        and binding["routing_key"] == ANALYSIS_REQUESTED_ROUTING_KEY
        for binding in main_bindings.json()
    )

    wait_bindings = await client.get(
        f"/api/queues/%2F/{WAIT_QUEUE}/bindings"
    )
    assert wait_bindings.status_code == 200
    assert any(
        binding["source"] == RETRY_EXCHANGE
        and binding["routing_key"] == MAIN_QUEUE
        for binding in wait_bindings.json()
    )


async def test_tutor_event_reaches_main_queue(rabbit):
    broker, channel, client = rabbit
    exchange = await channel.get_exchange(TUTOR_EVENTS_EXCHANGE)
    queue = await channel.get_queue(MAIN_QUEUE)
    analysis_id = "00000000-0000-4000-8000-000000000010"

    await exchange.publish(
        aio_pika.Message(body=event_body(analysis_id)),
        routing_key=ANALYSIS_REQUESTED_ROUTING_KEY,
    )

    message = await queue.get(timeout=5.0, fail=False)
    assert message is not None
    assert json.loads(message.body)["analysisId"] == analysis_id
    await message.ack()

    assert await _wait_for_messages(client, MAIN_QUEUE, 0) == 0
    assert broker.connected is True


async def test_retry_passes_through_wait_queue(rabbit):
    broker, channel, client = rabbit
    exchange = await channel.get_exchange(TUTOR_EVENTS_EXCHANGE)
    queue = await channel.get_queue(MAIN_QUEUE)
    analysis_id = "00000000-0000-4000-8000-000000000011"

    await exchange.publish(
        aio_pika.Message(body=event_body(analysis_id)),
        routing_key=ANALYSIS_REQUESTED_ROUTING_KEY,
    )
    message = await queue.get(timeout=5.0, fail=False)
    assert message is not None

    async def retry_handler(_body: bytes, _headers):
        return HandlerAction(ACTION_RETRY, retry_count=1)

    await broker._handle(message, retry_handler)

    # El mensaje original se confirmó y quedó esperando el TTL en .wait.
    assert await _wait_for_messages(client, WAIT_QUEUE, 1) == 1
    assert await _queue_messages(client, MAIN_QUEUE) == 0

    # Tras el TTL, el dead-letter lo devuelve a la cola principal.
    returned = await queue.get(timeout=RETRY_TTL_MS / 1000 + 5.0, fail=False)
    assert returned is not None
    assert returned.headers["x-retry-count"] == 1
    assert json.loads(returned.body)["analysisId"] == analysis_id
    await returned.ack()

    assert await _wait_for_messages(client, WAIT_QUEUE, 0) == 0
    assert broker.connected is True


async def test_invalid_message_goes_to_dlq(rabbit):
    broker, channel, _client = rabbit
    exchange = await channel.get_exchange(TUTOR_EVENTS_EXCHANGE)
    queue = await channel.get_queue(MAIN_QUEUE)
    dlq = await channel.get_queue(DLQ)
    body = b'{"eventType": "tutor.analysis.requested"'

    await exchange.publish(
        aio_pika.Message(body=body),
        routing_key=ANALYSIS_REQUESTED_ROUTING_KEY,
    )
    message = await queue.get(timeout=5.0, fail=False)
    assert message is not None

    handler = MessageHandler(processor=object(), maximum_depth=18)
    await broker._handle(message, handler.handle)

    discarded = await dlq.get(timeout=5.0, fail=False)
    assert discarded is not None
    assert discarded.body == body
    await discarded.ack()
