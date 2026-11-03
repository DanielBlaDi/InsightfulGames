"""Fixtures y dobles del Analysis Worker.

El repositorio falso es atómico y simula la hora de MongoDB. Se usa en lugar
de mongomock porque los pipelines del worker dependen de ``$$NOW``.
"""

from __future__ import annotations

import asyncio
import copy
import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import chess

from app.config import RETRY_DELAYS_SECONDS, Settings
from app.errors import AnalysisFailure

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
START_FEN = chess.STARTING_FEN


def new_uuid() -> str:
    return str(uuid.uuid4())


def build_settings(**overrides) -> Settings:
    values = dict(
        port=8089,
        gateway_internal_url="http://gateway.test",
        mongo_analysis_url="mongodb://unused",
        mongo_analysis_database="analysis_test",
        rabbitmq_url="amqp://unused",
        analysis_depth_max=18,
        analysis_max_retries=5,
        analysis_inaccuracy_cp=50,
        analysis_mistake_cp=100,
        analysis_blunder_cp=300,
        poll_interval_seconds=5.0,
        analysis_stale_minutes=5.0,
        http_timeout=5.0,
        log_level="WARNING",
        worker_id="worker-test",
    )
    values.update(overrides)
    return Settings(**values)


def make_analysis(
    *,
    analysis_id: str | None = None,
    game_id: str | None = None,
    status: str = "pending",
    depth: int = 15,
    claim_count: int = 0,
    updated_at: datetime = BASE_TIME,
    lease_until: datetime | None = None,
    lease_owner: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    analysis_id = analysis_id or new_uuid()
    game_id = game_id or new_uuid()
    document: dict[str, Any] = {
        "_id": analysis_id,
        "analysisId": analysis_id,
        "gameId": game_id,
        "engineVersion": "stockfish-15.1",
        "language": "es",
        "detailLevel": "standard",
        "depth": depth,
        "status": status,
        "requestedBy": new_uuid(),
        "participantIds": [],
        "error": None,
        "explanation": None,
        "createdAt": updated_at,
        "updatedAt": updated_at,
        "reactivations": 0,
    }
    if claim_count:
        document["claimCount"] = claim_count
    if lease_until is not None:
        document["leaseUntil"] = lease_until
    if lease_owner is not None:
        document["leaseOwner"] = lease_owner
    document.update(extra)
    return document


def make_game_input(
    game_id: str,
    *,
    moves: tuple[str, ...] = ("e2e4", "e7e5"),
    initial_fen: str = START_FEN,
    status: str = "finished",
    result: str = "white",
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "gameId": game_id,
        "initialFen": initial_fen,
        "status": status,
        "result": result,
        "moves": [
            {"ply": index, "uci": uci} for index, uci in enumerate(moves, start=1)
        ],
    }
    payload.update(extra)
    return payload


def evaluation_payload(
    value: int,
    *,
    evaluation_type: str = "cp",
    best_uci: str | None = None,
    best_san: str | None = None,
    depth: int = 15,
) -> dict[str, Any]:
    if best_uci is None:
        best_move = None
    else:
        best_move = {"uci": best_uci, "san": best_san or best_uci}
    return {
        "fen": START_FEN,
        "evaluation": {
            "type": evaluation_type,
            "value": value,
            "perspective": "white",
        },
        "bestMove": best_move,
        "depth": depth,
    }


def event_body(
    *,
    analysis_id: str | None = None,
    game_id: str | None = None,
    depth: int = 15,
    **overrides: Any,
) -> bytes:
    payload = {
        "eventId": new_uuid(),
        "eventType": "tutor.analysis.requested",
        "occurredAt": "2026-01-01T12:00:00Z",
        "analysisId": analysis_id or new_uuid(),
        "gameId": game_id or new_uuid(),
        "requestedBy": new_uuid(),
        "language": "es",
        "detailLevel": "standard",
        "depth": depth,
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


def transient(message: str = "El motor no respondió.") -> AnalysisFailure:
    return AnalysisFailure(message, failure_kind="transient", code="ENGINE_BUSY")


def permanent(message: str = "Datos inválidos.") -> AnalysisFailure:
    return AnalysisFailure(message, failure_kind="permanent")


async def noop_sleep(_seconds: float) -> None:
    return None


class FakeAnalysisRepository:
    """Repositorio atómico en memoria con reloj de base de datos simulado."""

    def __init__(
        self,
        documents: list[dict[str, Any]] | None = None,
        *,
        now: datetime = BASE_TIME,
    ):
        self._documents = {
            document["analysisId"]: copy.deepcopy(document)
            for document in (documents or [])
        }
        self.now = now
        self._lock = asyncio.Lock()
        self.renew_calls = 0
        self.renew_returns = True
        self.expire_on_finalize = False
        self.finalize_calls = 0

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def document(self, analysis_id: str) -> dict[str, Any] | None:
        document = self._documents.get(analysis_id)
        return copy.deepcopy(document) if document is not None else None

    async def healthy(self) -> bool:
        return True

    async def get(self, analysis_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return self.document(analysis_id)

    def _can_claim(self, document: dict[str, Any], max_claims: int) -> bool:
        claim_count = document.get("claimCount", 0)
        if claim_count >= max_claims:
            return False
        if document.get("status") == "pending":
            return True
        lease_until = document.get("leaseUntil")
        return (
            document.get("status") == "processing"
            and isinstance(lease_until, datetime)
            and lease_until < self.now
        )

    async def claim(
        self,
        analysis_id: str,
        owner: str,
        stale_seconds: float,
        max_claims: int,
    ) -> dict[str, Any] | None:
        async with self._lock:
            document = self._documents.get(analysis_id)
            if document is None or not self._can_claim(document, max_claims):
                return None
            document["status"] = "processing"
            document["leaseOwner"] = owner
            document["leaseUntil"] = self.now + timedelta(seconds=stale_seconds)
            document["claimCount"] = document.get("claimCount", 0) + 1
            document["startedAt"] = document.get("startedAt", self.now)
            document["updatedAt"] = self.now
            return copy.deepcopy(document)

    async def renew(
        self, analysis_id: str, owner: str, stale_seconds: float
    ) -> bool:
        async with self._lock:
            self.renew_calls += 1
            document = self._documents.get(analysis_id)
            if (
                not self.renew_returns
                or document is None
                or document.get("status") != "processing"
                or document.get("leaseOwner") != owner
            ):
                return False
            document["leaseUntil"] = self.now + timedelta(seconds=stale_seconds)
            document["updatedAt"] = self.now
            return True

    def _lease_is_valid(self, document: dict[str, Any], owner: str) -> bool:
        lease_until = document.get("leaseUntil")
        return (
            document.get("status") == "processing"
            and document.get("leaseOwner") == owner
            and isinstance(lease_until, datetime)
            and lease_until > self.now
        )

    async def finalize_completed(
        self, analysis_id: str, owner: str, result: dict[str, Any]
    ) -> bool:
        async with self._lock:
            self.finalize_calls += 1
            document = self._documents.get(analysis_id)
            if document is None:
                return False
            if self.expire_on_finalize:
                document["leaseUntil"] = self.now - timedelta(seconds=1)
            if not self._lease_is_valid(document, owner):
                return False
            document["result"] = copy.deepcopy(result)
            document["status"] = "completed"
            document["completedAt"] = self.now
            document["updatedAt"] = self.now
            document["error"] = None
            document.pop("leaseUntil", None)
            document.pop("leaseOwner", None)
            return True

    async def finalize_failed(
        self,
        analysis_id: str,
        owner: str,
        failure_kind: str,
        error: str,
    ) -> bool:
        async with self._lock:
            self.finalize_calls += 1
            document = self._documents.get(analysis_id)
            if document is None:
                return False
            if self.expire_on_finalize:
                document["leaseUntil"] = self.now - timedelta(seconds=1)
            if not self._lease_is_valid(document, owner):
                return False
            document["status"] = "failed"
            document["failureKind"] = failure_kind
            document["error"] = error
            document["completedAt"] = self.now
            document["updatedAt"] = self.now
            document.pop("leaseUntil", None)
            document.pop("leaseOwner", None)
            return True

    async def find_recoverable(
        self, stale_seconds: float, limit: int = 10
    ) -> list[dict[str, Any]]:
        async with self._lock:
            threshold = self.now - timedelta(seconds=stale_seconds)
            candidates = []
            for document in self._documents.values():
                if document.get("status") == "pending":
                    updated_at = document.get("updatedAt")
                    if isinstance(updated_at, datetime) and updated_at < threshold:
                        candidates.append(copy.deepcopy(document))
                elif document.get("status") == "processing":
                    lease_until = document.get("leaseUntil")
                    if isinstance(lease_until, datetime) and lease_until < self.now:
                        candidates.append(copy.deepcopy(document))
            candidates.sort(key=lambda item: item.get("updatedAt", self.now))
            return [
                {"analysisId": document["analysisId"]}
                for document in candidates[:limit]
            ]

    async def fail_exhausted(
        self,
        analysis_id: str,
        max_claims: int,
        stale_seconds: float,
        error: str,
    ) -> bool:
        async with self._lock:
            document = self._documents.get(analysis_id)
            if document is None:
                return False
            if document.get("claimCount", 0) < max_claims:
                return False
            threshold = self.now - timedelta(seconds=stale_seconds)
            eligible = (
                document.get("status") == "pending"
                and isinstance(document.get("updatedAt"), datetime)
                and document["updatedAt"] < threshold
            ) or (
                document.get("status") == "processing"
                and isinstance(document.get("leaseUntil"), datetime)
                and document["leaseUntil"] < self.now
            )
            if not eligible:
                return False
            document["status"] = "failed"
            document["failureKind"] = "transient"
            document["error"] = error
            document["completedAt"] = self.now
            document["updatedAt"] = self.now
            document.pop("leaseUntil", None)
            document.pop("leaseOwner", None)
            return True


class FakeGameLogic:
    def __init__(
        self,
        data: dict[str, Any] | None = None,
        error: Exception | None = None,
    ):
        self.data = data
        self.error = error
        self.calls: list[str] = []

    async def get_analysis_input(self, game_id: str) -> dict[str, Any]:
        self.calls.append(game_id)
        await asyncio.sleep(0)
        if self.error is not None:
            raise self.error
        if self.data is None:
            raise AssertionError("FakeGameLogic no tiene datos")
        return copy.deepcopy(self.data)


class FakeEngine:
    def __init__(
        self,
        responses: list[Any] | None = None,
        *,
        default: dict[str, Any] | None = None,
        delay: float = 0.0,
    ):
        self.responses = list(responses or [])
        self.default = default
        self.delay = delay
        self.calls: list[tuple[str, int]] = []

    async def evaluate(self, fen: str, depth: int) -> dict[str, Any]:
        self.calls.append((fen, depth))
        if self.delay:
            await asyncio.sleep(self.delay)
        else:
            await asyncio.sleep(0)
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            if callable(response):
                return response(fen, depth)
            return copy.deepcopy(response)
        if self.default is not None:
            return copy.deepcopy(self.default)
        raise AssertionError("FakeEngine no tiene respuesta")


class FakeBroker:
    def __init__(self):
        self.started = 0
        self.closed = 0
        self.retries: list[tuple[bytes, dict[str, Any] | None, int]] = []
        self.dlq: list[tuple[bytes, dict[str, Any] | None]] = []
        self._wait = asyncio.Event()

    async def start(self) -> None:
        self.started += 1

    async def consume(self, _handler) -> None:
        await self._wait.wait()

    async def close(self) -> None:
        self.closed += 1

    async def publish_retry(self, body, headers, retry_count, **_kwargs) -> None:
        self.retries.append((body, headers, retry_count))

    async def publish_dlq(self, body, headers, **_kwargs) -> None:
        self.dlq.append((body, headers))


def with_worker(settings: Settings, worker_id: str) -> Settings:
    return replace(settings, worker_id=worker_id)


def retry_delays() -> tuple[float, ...]:
    return RETRY_DELAYS_SECONDS
