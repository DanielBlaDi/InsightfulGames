"""Evento tutor.analysis.requested y tolerancia a un broker caído."""

from __future__ import annotations

import uuid

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
