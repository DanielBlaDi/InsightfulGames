"""Pruebas de la recuperación periódica y del límite de reclamos."""

from __future__ import annotations

from datetime import timedelta

from app.poller import EXHAUSTED_ERROR, AnalysisPoller
from tests.conftest import (
    BASE_TIME,
    FakeAnalysisRepository,
    build_settings,
    make_analysis,
    new_uuid,
)


class RecordingProcessor:
    """Simula el reclamo del procesador real para reflejar el estado final."""

    def __init__(
        self,
        repository: FakeAnalysisRepository | None = None,
        outcome: str = "completed",
    ):
        self.repository = repository
        self.outcome = outcome
        self.calls: list[str] = []

    async def process(self, analysis_id: str) -> str:
        self.calls.append(analysis_id)
        if self.repository is not None:
            await self.repository.claim(
                analysis_id, "recording-worker", 300.0, 5
            )
        return self.outcome


def old_document(**overrides):
    return make_analysis(
        updated_at=BASE_TIME - timedelta(minutes=6), **overrides
    )


async def test_recovers_old_pending_analysis():
    analysis = old_document()
    repository = FakeAnalysisRepository([analysis], now=BASE_TIME)
    processor = RecordingProcessor(repository)
    poller = AnalysisPoller(repository, processor, build_settings())

    processed = await poller.run_once()

    assert processed == 1
    assert processor.calls == [analysis["analysisId"]]
    document = repository.document(analysis["analysisId"])
    assert document["status"] == "processing"
    assert document["claimCount"] == 1


async def test_ignores_recent_pending_analysis():
    analysis = make_analysis(
        updated_at=BASE_TIME - timedelta(minutes=1)
    )
    repository = FakeAnalysisRepository([analysis], now=BASE_TIME)
    processor = RecordingProcessor(repository)
    poller = AnalysisPoller(repository, processor, build_settings())

    assert await poller.run_once() == 0
    assert processor.calls == []


async def test_recovers_processing_with_expired_lease():
    analysis = make_analysis(
        status="processing",
        claim_count=1,
        lease_owner="dead-worker",
        lease_until=BASE_TIME - timedelta(seconds=1),
        updated_at=BASE_TIME - timedelta(minutes=5),
    )
    repository = FakeAnalysisRepository([analysis], now=BASE_TIME)
    processor = RecordingProcessor(repository)
    poller = AnalysisPoller(repository, processor, build_settings())

    assert await poller.run_once() == 1
    assert processor.calls == [analysis["analysisId"]]


async def test_marks_failed_when_claim_limit_is_reached():
    analysis = old_document(claim_count=5)
    repository = FakeAnalysisRepository([analysis], now=BASE_TIME)
    processor = RecordingProcessor(repository)
    poller = AnalysisPoller(repository, processor, build_settings())

    assert await poller.run_once() == 0
    assert processor.calls == []
    document = repository.document(analysis["analysisId"])
    assert document["status"] == "failed"
    assert document["failureKind"] == "transient"
    assert document["error"] == EXHAUSTED_ERROR
    assert "leaseUntil" not in document


async def test_batch_is_limited_to_ten_analyses():
    documents = [old_document() for _ in range(12)]
    repository = FakeAnalysisRepository(documents, now=BASE_TIME)
    processor = RecordingProcessor(repository)
    poller = AnalysisPoller(repository, processor, build_settings())

    processed = await poller.run_once()

    assert processed == 10
    assert len(processor.calls) == 10
    statuses = [
        repository.document(document["analysisId"])["status"]
        for document in documents
    ]
    assert statuses.count("processing") == 10
    assert statuses.count("pending") == 2


async def test_a_processor_error_does_not_stop_the_batch():
    first = old_document()
    second = old_document()

    class FailingOnceProcessor(RecordingProcessor):
        async def process(self, analysis_id: str) -> str:
            self.calls.append(analysis_id)
            if analysis_id == first["analysisId"]:
                raise RuntimeError("Mongo no responde")
            return "completed"

    repository = FakeAnalysisRepository([first, second], now=BASE_TIME)
    processor = FailingOnceProcessor()
    poller = AnalysisPoller(repository, processor, build_settings())

    processed = await poller.run_once()

    assert processed == 1
    assert processor.calls == [first["analysisId"], second["analysisId"]]


async def test_poller_does_not_invent_ids():
    repository = FakeAnalysisRepository(
        [old_document(), old_document()], now=BASE_TIME
    )
    processor = RecordingProcessor(repository)
    poller = AnalysisPoller(repository, processor, build_settings())

    await poller.run_once()

    assert all(isinstance(call, str) and call for call in processor.calls)
    assert len(set(processor.calls)) == len(processor.calls)


def test_batch_limit_constant_is_ten():
    from app.poller import MAX_BATCH

    assert MAX_BATCH == 10


def test_new_uuid_is_a_string():
    assert isinstance(new_uuid(), str)
