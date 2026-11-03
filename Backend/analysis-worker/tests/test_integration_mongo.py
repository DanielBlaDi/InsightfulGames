"""Prueba de integración opcional con MongoDB real.

Se omite salvo que exista ``MONGO_TEST_URL``. No forma parte de la suite
habitual porque requiere una instancia MongoDB alcanzable y Docker todavía no
está disponible en el entorno de desarrollo.

Ejemplo de ejecución:

    $env:MONGO_TEST_URL = "mongodb://localhost:27017"
    python -m pytest -q tests/test_integration_mongo.py
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

from app.db import create_mongo_client
from app.repository import AnalysisRepository

MONGO_TEST_URL = os.getenv("MONGO_TEST_URL")
MONGO_TEST_DATABASE = os.getenv("MONGO_TEST_DATABASE", "analysis_worker_test")

pytestmark = pytest.mark.skipif(
    not MONGO_TEST_URL,
    reason="Define MONGO_TEST_URL para ejecutar la integración con MongoDB real.",
)


def analysis_document(analysis_id: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "_id": analysis_id,
        "analysisId": analysis_id,
        "gameId": str(uuid.uuid4()),
        "status": "pending",
        "depth": 15,
        "claimCount": 0,
        "createdAt": now,
        "updatedAt": now,
    }


async def test_claim_renew_and_finalize_with_real_mongo():
    client = create_mongo_client(MONGO_TEST_URL)
    collection_name = f"analyses_it_{uuid.uuid4().hex}"
    database = client[MONGO_TEST_DATABASE]
    repository = AnalysisRepository(database, collection_name)
    analysis_id = str(uuid.uuid4())

    try:
        await database[collection_name].insert_one(analysis_document(analysis_id))

        first = await repository.claim(analysis_id, "worker-a", 300.0, 5)
        assert first is not None
        assert first["status"] == "processing"
        assert first["leaseOwner"] == "worker-a"
        assert first["claimCount"] == 1

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
        assert "leaseOwner" not in document
        assert "leaseUntil" not in document

        # Un mensaje duplicado no vuelve a reclamar un análisis terminado.
        assert await repository.claim(analysis_id, "worker-c", 300.0, 5) is None
    finally:
        await database.drop_collection(collection_name)
        client.close()
