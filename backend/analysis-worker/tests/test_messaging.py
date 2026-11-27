"""Pruebas de la política de confirmación y reintentos del broker."""

from __future__ import annotations

import pytest

from app.messaging import (
    ACTION_ACK,
    ACTION_DLQ,
    ACTION_RETRY,
    MessageHandler,
)
from tests.conftest import event_body, new_uuid


class StubProcessor:
    def __init__(self, *, error: Exception | None = None, outcome: str = "completed"):
        self.error = error
        self.outcome = outcome
        self.calls: list[str] = []

    async def process(self, analysis_id: str) -> str:
        self.calls.append(analysis_id)
        if self.error is not None:
            raise self.error
        return self.outcome


@pytest.mark.parametrize(
    "body",
    [
        b"no es json",
        b"{}",
        b"[]",
        b'{"eventType": "otro"}',
    ],
)
async def test_invalid_messages_go_directly_to_dlq(body):
    processor = StubProcessor()
    handler = MessageHandler(processor, maximum_depth=18)

    action = await handler.handle(body, {})

    assert action.kind == ACTION_DLQ
    assert processor.calls == []


async def test_depth_above_maximum_is_invalid():
    processor = StubProcessor()
    handler = MessageHandler(processor, maximum_depth=18)

    action = await handler.handle(event_body(depth=19), {})

    assert action.kind == ACTION_DLQ
    assert processor.calls == []


async def test_valid_message_is_acknowledged_after_processing():
    analysis_id = new_uuid()
    processor = StubProcessor()
    handler = MessageHandler(processor, maximum_depth=18)

    action = await handler.handle(event_body(analysis_id=analysis_id), {})

    assert action.kind == ACTION_ACK
    assert processor.calls == [analysis_id]


@pytest.mark.parametrize(
    "headers",
    [None, {}, {"x-retry-count": 0}, {"x-retry-count": "0"}],
)
async def test_infrastructure_failure_starts_broker_retry_at_one(headers):
    processor = StubProcessor(error=RuntimeError("Mongo caído"))
    handler = MessageHandler(processor, maximum_depth=18)

    action = await handler.handle(event_body(), headers)

    assert action.kind == ACTION_RETRY
    assert action.retry_count == 1


async def test_retry_counter_increments_and_accepts_strings():
    processor = StubProcessor(error=RuntimeError("Mongo caído"))
    handler = MessageHandler(processor, maximum_depth=18)

    action = await handler.handle(
        event_body(), {"x-retry-count": "4"}
    )

    assert action.kind == ACTION_RETRY
    assert action.retry_count == 5


async def test_after_five_retries_the_message_goes_to_dlq():
    processor = StubProcessor(error=RuntimeError("Mongo caído"))
    handler = MessageHandler(processor, maximum_depth=18)

    action = await handler.handle(
        event_body(), {"x-retry-count": 5}
    )

    assert action.kind == ACTION_DLQ


async def test_negative_retry_counter_is_treated_as_zero():
    processor = StubProcessor(error=RuntimeError("Mongo caído"))
    handler = MessageHandler(processor, maximum_depth=18)

    action = await handler.handle(
        event_body(), {"x-retry-count": -3}
    )

    assert action.kind == ACTION_RETRY
    assert action.retry_count == 1
