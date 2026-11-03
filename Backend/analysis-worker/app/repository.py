"""Repositorio de la colección ``analyses``.

El Analysis Worker solo puede escribir los campos acotados del contrato
(sección 17.5). Todas las operaciones sensibles al tiempo usan ``$$NOW`` para
no depender del reloj de cada proceso:

* reclamo atómico y renovación del lease;
* escritura final condicionada por dueño y lease vigente;
* recuperación de ``pending`` antiguos y ``processing`` con lease vencido.
"""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ReturnDocument

LOGGER = logging.getLogger("analysis-worker.repository")

COLLECTION_NAME = "analyses"


def _stale_ms(stale_seconds: float) -> int:
    return int(stale_seconds * 1000)


class AnalysisRepository:
    def __init__(
        self,
        database: AsyncIOMotorDatabase,
        collection_name: str = COLLECTION_NAME,
    ):
        self._database = database
        self._collection: AsyncIOMotorCollection = database[collection_name]

    @property
    def collection(self) -> AsyncIOMotorCollection:
        return self._collection

    async def healthy(self) -> bool:
        """Comprueba MongoDB. No comprueba el broker (sección 17.2)."""
        try:
            await self._collection.find_one({}, {"_id": 1})
            return True
        except Exception:  # pragma: no cover - depende de la red/Mongo
            LOGGER.exception("MongoDB de análisis no responde")
            return False

    async def get(self, analysis_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one({"analysisId": analysis_id})

    async def claim(
        self,
        analysis_id: str,
        owner: str,
        stale_seconds: float,
        max_claims: int,
    ) -> dict[str, Any] | None:
        """Reclama el análisis de forma atómica (sección 17.4.1).

        Solo toma un ``pending`` o un ``processing`` con lease vencido. No
        reclama si ya se alcanzó el límite de reclamos.
        """
        stale_ms = _stale_ms(stale_seconds)
        pipeline = [
            {"$set": {"_now": "$$NOW"}},
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            {
                                "$or": [
                                    {"$eq": ["$status", "pending"]},
                                    {
                                        "$and": [
                                            {"$eq": ["$status", "processing"]},
                                            {"$lt": ["$leaseUntil", "$$NOW"]},
                                        ]
                                    },
                                ]
                            },
                            {
                                "$lt": [
                                    {"$ifNull": ["$claimCount", 0]},
                                    max_claims,
                                ]
                            },
                        ]
                    }
                }
            },
            {
                "$set": {
                    "status": "processing",
                    "leaseOwner": owner,
                    "leaseUntil": {"$add": ["$_now", stale_ms]},
                    "claimCount": {
                        "$add": [{"$ifNull": ["$claimCount", 0]}, 1]
                    },
                    "startedAt": {"$ifNull": ["$startedAt", "$_now"]},
                    "updatedAt": "$_now",
                }
            },
            {"$unset": ["_now"]},
        ]
        return await self._collection.find_one_and_update(
            {"analysisId": analysis_id},
            pipeline,
            return_document=ReturnDocument.AFTER,
        )

    async def renew(
        self, analysis_id: str, owner: str, stale_seconds: float
    ) -> bool:
        """Renueva el lease solo si el worker sigue siendo el dueño."""
        stale_ms = _stale_ms(stale_seconds)
        pipeline = [
            {"$set": {"_now": "$$NOW"}},
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$status", "processing"]},
                            {"$eq": ["$leaseOwner", owner]},
                        ]
                    }
                }
            },
            {
                "$set": {
                    "leaseUntil": {"$add": ["$_now", stale_ms]},
                    "updatedAt": "$_now",
                }
            },
            {"$unset": ["_now"]},
        ]
        result = await self._collection.update_one(
            {"analysisId": analysis_id}, pipeline
        )
        return result.modified_count == 1

    async def finalize_completed(
        self, analysis_id: str, owner: str, result: dict[str, Any]
    ) -> bool:
        """Escribe el resultado solo si el lease sigue vigente y es del dueño."""
        pipeline = [
            {"$set": {"_now": "$$NOW"}},
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$status", "processing"]},
                            {"$eq": ["$leaseOwner", owner]},
                            {"$gt": ["$leaseUntil", "$$NOW"]},
                        ]
                    }
                }
            },
            {
                "$set": {
                    "result": result,
                    "status": "completed",
                    "completedAt": "$_now",
                    "updatedAt": "$_now",
                    "error": None,
                }
            },
            {"$unset": ["_now", "leaseUntil", "leaseOwner"]},
        ]
        update = await self._collection.update_one(
            {"analysisId": analysis_id}, pipeline
        )
        return update.modified_count == 1

    async def finalize_failed(
        self,
        analysis_id: str,
        owner: str,
        failure_kind: str,
        error: str,
    ) -> bool:
        """Marca ``failed`` solo si el lease sigue vigente y es del dueño."""
        pipeline = [
            {"$set": {"_now": "$$NOW"}},
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            {"$eq": ["$status", "processing"]},
                            {"$eq": ["$leaseOwner", owner]},
                            {"$gt": ["$leaseUntil", "$$NOW"]},
                        ]
                    }
                }
            },
            {
                "$set": {
                    "status": "failed",
                    "failureKind": failure_kind,
                    "error": error,
                    "completedAt": "$_now",
                    "updatedAt": "$_now",
                }
            },
            {"$unset": ["_now", "leaseUntil", "leaseOwner"]},
        ]
        update = await self._collection.update_one(
            {"analysisId": analysis_id}, pipeline
        )
        return update.modified_count == 1

    async def find_recoverable(
        self, stale_seconds: float, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Lista pending antiguos y processing con lease vencido."""
        stale_ms = _stale_ms(stale_seconds)
        pipeline = [
            {"$set": {"_now": "$$NOW"}},
            {
                "$match": {
                    "$expr": {
                        "$or": [
                            {
                                "$and": [
                                    {"$eq": ["$status", "pending"]},
                                    {
                                        "$lt": [
                                            "$updatedAt",
                                            {"$subtract": ["$$NOW", stale_ms]},
                                        ]
                                    },
                                ]
                            },
                            {
                                "$and": [
                                    {"$eq": ["$status", "processing"]},
                                    {"$lt": ["$leaseUntil", "$$NOW"]},
                                ]
                            },
                        ]
                    }
                }
            },
            {"$sort": {"updatedAt": 1}},
            {"$limit": limit},
            {"$project": {"_id": 0, "analysisId": 1}},
        ]
        return [document async for document in self._collection.aggregate(pipeline)]

    async def fail_exhausted(
        self,
        analysis_id: str,
        max_claims: int,
        stale_seconds: float,
        error: str,
    ) -> bool:
        """Pasa a failed un análisis que agotó el límite de reclamos."""
        stale_ms = _stale_ms(stale_seconds)
        pipeline = [
            {"$set": {"_now": "$$NOW"}},
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            {
                                "$gte": [
                                    {"$ifNull": ["$claimCount", 0]},
                                    max_claims,
                                ]
                            },
                            {
                                "$or": [
                                    {
                                        "$and": [
                                            {"$eq": ["$status", "pending"]},
                                            {
                                                "$lt": [
                                                    "$updatedAt",
                                                    {
                                                        "$subtract": [
                                                            "$$NOW",
                                                            stale_ms,
                                                        ]
                                                    },
                                                ]
                                            },
                                        ]
                                    },
                                    {
                                        "$and": [
                                            {"$eq": ["$status", "processing"]},
                                            {"$lt": ["$leaseUntil", "$$NOW"]},
                                        ]
                                    },
                                ]
                            },
                        ]
                    }
                }
            },
            {
                "$set": {
                    "status": "failed",
                    "failureKind": "transient",
                    "error": error,
                    "completedAt": "$_now",
                    "updatedAt": "$_now",
                }
            },
            {"$unset": ["_now", "leaseUntil", "leaseOwner"]},
        ]
        update = await self._collection.update_one(
            {"analysisId": analysis_id}, pipeline
        )
        return update.modified_count == 1
