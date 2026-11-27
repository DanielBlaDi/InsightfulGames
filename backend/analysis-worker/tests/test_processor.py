"""Pruebas del procesador: resultado, reintentos, lease y carreras."""

from __future__ import annotations

import asyncio

import pytest

from app.processor import (
    OUTCOME_COMPLETED,
    OUTCOME_DISCARDED,
    OUTCOME_FAILED_PERMANENT,
    OUTCOME_FAILED_TRANSIENT,
    OUTCOME_LEASE_LOST,
    OUTCOME_SKIPPED,
    AnalysisProcessor,
)
from tests.conftest import (
    FakeAnalysisRepository,
    FakeEngine,
    FakeGameLogic,
    build_settings,
    evaluation_payload,
    make_analysis,
    make_game_input,
    noop_sleep,
    permanent,
    transient,
    with_worker,
)


def build_processor(
    repository: FakeAnalysisRepository,
    game_logic: FakeGameLogic,
    engine: FakeEngine,
    settings=None,
    *,
    retry_sleep=noop_sleep,
) -> AnalysisProcessor:
    return AnalysisProcessor(
        repository,
        game_logic,
        engine,
        settings or build_settings(),
        retry_sleep=retry_sleep,
    )


def success_responses() -> list[dict]:
    return [
        evaluation_payload(20, best_uci="e2e4", best_san="e4"),
        evaluation_payload(15, best_uci="e7e5", best_san="e5"),
        evaluation_payload(10, best_uci="g1f3", best_san="Nf3"),
    ]


async def test_completed_writes_result_and_clears_lease():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine(success_responses())

    outcome = await build_processor(repository, game_logic, engine).process(
        analysis["analysisId"]
    )

    assert outcome == OUTCOME_COMPLETED
    document = repository.document(analysis["analysisId"])
    assert document["status"] == "completed"
    assert document["claimCount"] == 1
    assert document["result"]["summary"]["white"]["best"] == 1
    assert document["result"]["summary"]["black"]["best"] == 1
    assert len(document["result"]["moves"]) == 2
    assert "leaseUntil" not in document
    assert "leaseOwner" not in document
    assert document["completedAt"] is not None
    assert document["error"] is None
    assert len(engine.calls) == 3
    assert all(depth == analysis["depth"] for _fen, depth in engine.calls)
    assert game_logic.calls == [analysis["gameId"]]


async def test_skipped_when_another_worker_has_the_lease():
    analysis = make_analysis(
        status="processing",
        claim_count=1,
        lease_owner="other-worker",
    )
    analysis["leaseUntil"] = analysis["updatedAt"].replace(year=2030)
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine(success_responses())

    outcome = await build_processor(repository, game_logic, engine).process(
        analysis["analysisId"]
    )

    assert outcome == OUTCOME_SKIPPED
    assert engine.calls == []


async def test_transient_engine_failure_is_retried_with_contract_delays():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine([transient("ocupado"), *success_responses()])
    delays: list[float] = []

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    outcome = await build_processor(
        repository, game_logic, engine, retry_sleep=sleep
    ).process(analysis["analysisId"])

    assert outcome == OUTCOME_COMPLETED
    assert delays == [1.0]
    assert len(engine.calls) == 4


async def test_transient_engine_exhaustion_marks_failed_transient():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine(
        [transient("busy-1"), transient("busy-2"), transient("busy-3")]
    )
    delays: list[float] = []

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    outcome = await build_processor(
        repository,
        game_logic,
        engine,
        build_settings(analysis_max_retries=3),
        retry_sleep=sleep,
    ).process(analysis["analysisId"])

    assert outcome == OUTCOME_FAILED_TRANSIENT
    document = repository.document(analysis["analysisId"])
    assert document["status"] == "failed"
    assert document["failureKind"] == "transient"
    assert document["error"] == "busy-3"
    assert "leaseUntil" not in document
    assert delays == [1.0, 2.0]
    assert len(engine.calls) == 3


async def test_permanent_engine_failure_is_not_retried():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine([permanent("posición inválida")])

    outcome = await build_processor(repository, game_logic, engine).process(
        analysis["analysisId"]
    )

    assert outcome == OUTCOME_FAILED_PERMANENT
    document = repository.document(analysis["analysisId"])
    assert document["failureKind"] == "permanent"
    assert document["error"] == "posición inválida"
    assert len(engine.calls) == 1


async def test_transient_input_failure_marks_failed_transient():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(error=transient("Game Logic caído"))
    engine = FakeEngine(success_responses())

    outcome = await build_processor(repository, game_logic, engine).process(
        analysis["analysisId"]
    )

    assert outcome == OUTCOME_FAILED_TRANSIENT
    assert repository.document(analysis["analysisId"])["failureKind"] == "transient"
    assert engine.calls == []


async def test_permanent_input_failure_marks_failed_permanent():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(error=permanent("GAME_NOT_FINISHED"))
    engine = FakeEngine(success_responses())

    outcome = await build_processor(repository, game_logic, engine).process(
        analysis["analysisId"]
    )

    assert outcome == OUTCOME_FAILED_PERMANENT
    assert repository.document(analysis["analysisId"])["failureKind"] == "permanent"
    assert engine.calls == []


async def test_invalid_fen_marks_failed_permanent():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(
        make_game_input(analysis["gameId"], initial_fen="fen-invalida")
    )
    engine = FakeEngine(success_responses())

    outcome = await build_processor(repository, game_logic, engine).process(
        analysis["analysisId"]
    )

    assert outcome == OUTCOME_FAILED_PERMANENT
    assert engine.calls == []


async def test_two_workers_only_process_once():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine(success_responses())

    settings_a = with_worker(build_settings(), "worker-a")
    settings_b = with_worker(build_settings(), "worker-b")
    processor_a = build_processor(repository, game_logic, engine, settings_a)
    processor_b = build_processor(repository, game_logic, engine, settings_b)

    outcomes = await asyncio.gather(
        processor_a.process(analysis["analysisId"]),
        processor_b.process(analysis["analysisId"]),
    )

    assert sorted(outcomes) == sorted([OUTCOME_COMPLETED, OUTCOME_SKIPPED])
    assert len(engine.calls) == 3
    assert repository.document(analysis["analysisId"])["claimCount"] == 1


async def test_a_single_processor_works_on_one_analysis_at_a_time():
    first = make_analysis()
    second = make_analysis(game_id=first["gameId"])

    class ConcurrencyProbeEngine:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0

        async def evaluate(self, fen: str, depth: int) -> dict:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return evaluation_payload(0, best_uci="e2e4", best_san="e4")

    repository = FakeAnalysisRepository([first, second])
    game_logic = FakeGameLogic(make_game_input(first["gameId"]))
    engine = ConcurrencyProbeEngine()
    processor = build_processor(repository, game_logic, engine)

    outcomes = await asyncio.gather(
        processor.process(first["analysisId"]),
        processor.process(second["analysisId"]),
    )

    assert outcomes == [OUTCOME_COMPLETED, OUTCOME_COMPLETED]
    assert engine.max_active == 1


async def test_result_is_discarded_when_lease_expires_before_final_write():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    repository.expire_on_finalize = True
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine(success_responses())

    outcome = await build_processor(repository, game_logic, engine).process(
        analysis["analysisId"]
    )

    assert outcome == OUTCOME_DISCARDED
    document = repository.document(analysis["analysisId"])
    assert document["status"] == "processing"
    assert "result" not in document
    assert repository.finalize_calls == 1


async def test_worker_aborts_when_renewal_fails():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    repository.renew_returns = False
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine(success_responses(), delay=0.12)

    outcome = await build_processor(
        repository,
        game_logic,
        engine,
        build_settings(analysis_stale_minutes=0.001),
    ).process(analysis["analysisId"])

    assert outcome == OUTCOME_LEASE_LOST
    assert repository.renew_calls >= 1
    assert repository.finalize_calls == 0
    assert len(engine.calls) == 1


async def test_worker_renews_lease_during_long_evaluation():
    analysis = make_analysis()
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine(success_responses(), delay=0.06)

    outcome = await build_processor(
        repository,
        game_logic,
        engine,
        build_settings(analysis_stale_minutes=0.001),
    ).process(analysis["analysisId"])

    assert outcome == OUTCOME_COMPLETED
    assert repository.renew_calls >= 1


async def test_claim_limit_prevents_processing():
    analysis = make_analysis(claim_count=5)
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine(success_responses())

    outcome = await build_processor(repository, game_logic, engine).process(
        analysis["analysisId"]
    )

    assert outcome == OUTCOME_SKIPPED
    assert engine.calls == []


async def test_invalid_depth_in_document_fails_permanently():
    analysis = make_analysis(depth=99)
    repository = FakeAnalysisRepository([analysis])
    game_logic = FakeGameLogic(make_game_input(analysis["gameId"]))
    engine = FakeEngine(success_responses())

    outcome = await build_processor(repository, game_logic, engine).process(
        analysis["analysisId"]
    )

    assert outcome == OUTCOME_FAILED_PERMANENT
    assert repository.document(analysis["analysisId"])["failureKind"] == "permanent"
    assert engine.calls == []
