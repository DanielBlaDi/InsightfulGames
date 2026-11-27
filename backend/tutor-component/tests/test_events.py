"""Evento tutor.analysis.requested y tolerancia a un broker caído."""

from __future__ import annotations

import uuid

import aio_pika

from app.events import EventPublisher, build_event_payload

ANALYSIS = {
    "analysisId": "11111111-1111-4111-8111-111111111111",
    "gameId": "22222222-2222-4222-8222-222222222222",
    "requestedBy": "33333333-3333-4333-8333-333333333333",
    "language": "es",
    "detailLevel": "standard",
    "depth": 15,
}


def test_payload_del_evento_cumple_la_seccion_17():
    payload = build_event_payload(ANALYSIS)

    assert set(payload) == {
        "eventId",
        "eventType",
        "occurredAt",
        "analysisId",
        "gameId",
        "requestedBy",
        "language",
        "detailLevel",
        "depth",
    }
    assert payload["eventType"] == "tutor.analysis.requested"
    assert uuid.UUID(payload["eventId"])
    assert payload["occurredAt"].endswith("Z")
    assert payload["analysisId"] == ANALYSIS["analysisId"]
    assert payload["depth"] == 15


async def test_publicador_devuelve_false_si_el_broker_no_esta():
    publisher = EventPublisher(
        "amqp://guest:guest@127.0.0.1:1/", timeout=0.5
    )
    try:
        assert await publisher.publish_analysis_requested(ANALYSIS) is False
        assert publisher.connected is False
    finally:
        await publisher.close()


class _FakeExchange:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, message, **kwargs):
        self.published.append(kwargs)


class _FakeChannel:
    def __init__(self) -> None:
        self.exchange = _FakeExchange()

    async def declare_exchange(self, *_args, **_kwargs):
        return self.exchange


class _FakeConnection:
    def __init__(self) -> None:
        self.is_closed = False
        self.channel_kwargs: dict | None = None
        self.fake_channel = _FakeChannel()

    async def channel(self, **kwargs):
        self.channel_kwargs = kwargs
        return self.fake_channel

    async def close(self):
        self.is_closed = True


async def test_publicacion_confirma_usa_mandatory_y_no_reintenta(monkeypatch):
    connection = _FakeConnection()

    async def fake_connect(*_args, **_kwargs):
        return connection

    monkeypatch.setattr(aio_pika, "connect_robust", fake_connect)
    publisher = EventPublisher("amqp://unused")

    try:
        assert await publisher.start() is True
        assert connection.channel_kwargs == {
            "publisher_confirms": True,
            "on_return_raises": True,
        }

        assert await publisher.publish_analysis_requested(ANALYSIS) is True
        published = connection.fake_channel.exchange.published
        assert len(published) == 1
        assert published[0]["mandatory"] is True
        assert published[0]["routing_key"] == "tutor.analysis.requested"
    finally:
        await publisher.close()
