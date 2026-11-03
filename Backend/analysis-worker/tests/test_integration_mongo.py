"""Pruebas de integración opcionales con MongoDB real.

Se omiten salvo que exista ``MONGO_TEST_URL``. No forman parte de la suite
habitual porque requieren una instancia MongoDB alcanzable.

Ejemplo de ejecución:

    $env:MONGO_TEST_URL = "mongodb://127.0.0.1:27018"
    $env:MONGO_TEST_DATABASE = "analysis_worker_it"
    python -m pytest -q tests/test_integration_mongo.py

Cada prueba usa una colección temporal y la elimina al terminar. No debe
apuntar a una base con datos reales.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import create_mongo_client
from app.repository import AnalysisRepository

MONGO_TEST_URL = os.getenv("MONGO_TEST_URL")
MONGO_TEST_DATABASE = os.getenv("MONGO_TEST_DATABASE", "analysis_worker_test")

pytestmark = pytest.mark.skipif(
    not MONGO_TEST_URL,
    reason="Define MONGO_TEST_URL para ejecutar la integración con MongoDB real.",
)


def analysis_document(
    analysis_id: str,
    *,
    status: str = "pending",
    claim_count: int = 0,
    lease_owner: str | None = None,
    lease_until: datetime | None = None,
    updated_at: datetime | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    document = {
        "_id": analysis_id,
        "analysisId": analysis_id,
        "gameId": str(uuid.uuid4()),
        "status": status,
        "depth": 15,
        "claimCount": claim_count,
        "createdAt": now,
        "updatedAt": updated_at or now,
    }
    if lease_owner is not None:
        document["leaseOwner"] = lease_owner
    if lease_until is not None:
        document["leaseUntil"] = lease_until
    return document


async def with_repository(test):
    """Crea una colección temporal y la elimina al terminar."""
    client = create_mongo_client(MONGO_TEST_URL)
    collection_name = f"analyses_it_{uuid.uuid4().hex}"
    database = client[MONGO_TEST_DATABASE]
    repository = AnalysisRepository(database, collection_name)
    try:
        await test(database, repository, collection_name)
    finally:
        await database.drop_collection(collection_name)
        client.close()


async def test_claim_renew_and_finalize_with_real_mongo():
    async def scenario(database, repository, collection_name):
        analysis_id = str(uuid.uuid4())
        await database[collection_name].insert_one(analysis_document(analysis_id))
        before = datetime.now(timezone.utc)

        first = await repository.claim(analysis_id, "worker-a", 300.0, 5)
        assert first is not None
        assert first["status"] == "processing"
        assert first["leaseOwner"] == "worker-a"
        assert first["claimCount"] == 1
        assert first["startedAt"] is not None
        assert before + timedelta(seconds=299) < first["leaseUntil"]

        # Otro worker no puede reclamar mientras el lease está vigente.
        assert await repository.claim(analysis_id, "worker-b", 300.0, 5) is None

        # Solo el dueño renueva y escribe.
        assert await repository.renew(analysis_id, "worker-a", 300.0) is True
        assert await repository.renew(analysis_id, "worker-b", 300.0) is False
        assert (
            await repository.finalize_completed(
                analysis_id, "worker-b", {"summary": {}, "moves": []}
            )
            is False
        )
        assert (
            await repository.finalize_completed(
                analysis_id,
                "worker-a",
                {"summary": {"white": {}, "black": {}}, "moves": []},
            )
            is True
        )

        document = await repository.get(analysis_id)
        assert document["status"] == "completed"
        assert document["result"]["moves"] == []
        assert document["completedAt"] is not None
        assert "leaseOwner" not in document
        assert "leaseUntil" not in document

        # Un mensaje duplicado no vuelve a reclamar un análisis terminado.
        assert await repository.claim(analysis_id, "worker-c", 300.0, 5) is None

    await with_repository(scenario)


async def test_expired_lease_is_reclaimed_and_late_writes_rejected():
    async def scenario(database, repository, collection_name):
        analysis_id = str(uuid.uuid4())
        await database[collection_name].insert_one(analysis_document(analysis_id))
        assert await repository.claim(analysis_id, "worker-a", 300.0, 5) is not None

        # Simula que el worker-a se quedó colgado y su lease venció.
        await database[collection_name].update_one(
            {"analysisId": analysis_id},
            {"$set": {"leaseUntil": datetime.now(timezone.utc) - timedelta(seconds=5)}},
        )

        # Un worker atrasado no puede escribir con el lease vencido.
        assert (
            await repository.finalize_completed(
                analysis_id, "worker-a", {"summary": {}, "moves": []}
            )
            is False
        )
        document = await repository.get(analysis_id)
        assert document["status"] == "processing"
        assert "result" not in document

        # El lease vencido permite que otro worker lo reclame.
        second = await repository.claim(analysis_id, "worker-b", 300.0, 5)
        assert second is not None
        assert second["leaseOwner"] == "worker-b"
        assert second["claimCount"] == 2

        # El dueño anterior ya no puede renovar ni finalizar.
        assert await repository.renew(analysis_id, "worker-a", 300.0) is False
        assert (
            await repository.finalize_completed(
                analysis_id, "worker-a", {"summary": {}, "moves": []}
            )
            is False
        )
        assert (
            await repository.finalize_completed(
                analysis_id,
                "worker-b",
                {"summary": {"white": {}, "black": {}}, "moves": []},
            )
            is True
        )

    await with_repository(scenario)


async def test_claim_respects_max_claims():
    async def scenario(database, repository, collection_name):
        analysis_id = str(uuid.uuid4())
        await database[collection_name].insert_one(
            analysis_document(
                analysis_id,
                status="processing",
                claim_count=5,
                lease_owner="worker-a",
                lease_until=datetime.now(timezone.utc) - timedelta(seconds=5),
            )
        )

        assert await repository.claim(analysis_id, "worker-b", 300.0, 5) is None
        document = await repository.get(analysis_id)
        assert document["status"] == "processing"
        assert document["claimCount"] == 5

    await with_repository(scenario)


async def test_find_recoverable_returns_only_stale_documents():
    async def scenario(database, repository, collection_name):
        now = datetime.now(timezone.utc)
        stale = 10.0
        pending_old = str(uuid.uuid4())
        pending_fresh = str(uuid.uuid4())
        processing_expired = str(uuid.uuid4())
        processing_valid = str(uuid.uuid4())
        completed = str(uuid.uuid4())

        await database[collection_name].insert_many(
            [
                analysis_document(
                    pending_old,
                    updated_at=now - timedelta(seconds=30),
                ),
                analysis_document(pending_fresh, updated_at=now),
                analysis_document(
                    processing_expired,
                    status="processing",
                    claim_count=1,
                    lease_owner="worker-a",
                    lease_until=now - timedelta(seconds=5),
                    updated_at=now - timedelta(seconds=5),
                ),
                analysis_document(
                    processing_valid,
                    status="processing",
                    claim_count=1,
                    lease_owner="worker-b",
                    lease_until=now + timedelta(seconds=300),
                ),
                analysis_document(completed, status="completed"),
            ]
        )

        recoverable = await repository.find_recoverable(stale, limit=10)
        ids = {document["analysisId"] for document in recoverable}
        assert ids == {pending_old, processing_expired}

    await with_repository(scenario)


async def test_fail_exhausted_marks_failed_once():
    async def scenario(database, repository, collection_name):
        analysis_id = str(uuid.uuid4())
        await database[collection_name].insert_one(
            analysis_document(
                analysis_id,
                status="processing",
                claim_count=5,
                lease_owner="worker-a",
                lease_until=datetime.now(timezone.utc) - timedelta(seconds=5),
            )
        )

        assert (
            await repository.fail_exhausted(
                analysis_id, 5, 300.0, "Se agotaron los reclamos"
            )
            is True
        )
        document = await repository.get(analysis_id)
        assert document["status"] == "failed"
        assert document["failureKind"] == "transient"
        assert document["error"] == "Se agotaron los reclamos"
        assert document["completedAt"] is not None
        assert "leaseOwner" not in document
        assert "leaseUntil" not in document

        # Ya no está en estado recuperable ni se vuelve a marcar.
        assert (
            await repository.fail_exhausted(
                analysis_id, 5, 300.0, "Se agotaron los reclamos"
            )
            is False
        )

    await with_repository(scenario)
