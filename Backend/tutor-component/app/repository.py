"""Repositorio de la colección ``analyses`` (MongoDB de análisis)."""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.config import ANONYMOUS_USER_ID

LOGGER = logging.getLogger("tutor.repository")

COLLECTION_NAME = "analyses"

# Clave de análisis del contrato: (gameId, engineVersion, language, detailLevel, depth).
# La sección 18 omite depth en el índice, pero las secciones 13 y 14 la incluyen
# en la clave y el propio contrato pide subir ENGINE_VERSION al cambiar umbrales.
KEY_FIELDS = ("gameId", "engineVersion", "language", "detailLevel", "depth")


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

    async def ensure_indexes(self) -> None:
        """Crea los índices del Tutor.

        El índice único es lo que garantiza la idempotencia ante dos POST
        simultáneos con la misma clave (sección 14). El nombre es explícito
        para que un cambio de clave falle de forma visible.
        """
        await self._collection.create_index(
            [(field, 1) for field in KEY_FIELDS],
            unique=True,
            name="uq_analyses_key",
        )
        await self._collection.create_index(
            [("requestedBy", 1), ("createdAt", -1)],
            name="ix_analyses_requested_by_created",
        )

    async def healthy(self) -> bool:
        try:
            await self._collection.find_one({}, {"_id": 1})
            return True
        except Exception:  # pragma: no cover - depende de la red/Mongo
            LOGGER.exception("MongoDB de análisis no responde")
            return False

    async def find_by_key(
        self,
        game_id: str,
        engine_version: str,
        language: str,
        detail_level: str,
        depth: int,
    ) -> dict[str, Any] | None:
        return await self._collection.find_one(
            {
                "gameId": game_id,
                "engineVersion": engine_version,
                "language": language,
                "detailLevel": detail_level,
                "depth": depth,
            }
        )

    async def get(self, analysis_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one({"analysisId": analysis_id})

    async def insert(self, document: dict[str, Any]) -> bool:
        """Inserta el análisis. Devuelve False si la clave ya existe."""
        try:
            await self._collection.insert_one(document)
            return True
        except DuplicateKeyError:
            return False
        except Exception:
            LOGGER.exception("No se pudo insertar el análisis %s", document.get("analysisId"))
            raise

    async def save_explanation(self, analysis_id: str, explanation: str) -> None:
        await self._collection.update_one(
            {"analysisId": analysis_id},
            {"$set": {"explanation": explanation}},
        )

    async def anonymize_requested_by(self, user_id: str) -> int:
        """Reemplaza requestedBy por el valor anónimo (borrado de cuenta)."""
        if user_id == ANONYMOUS_USER_ID:
            return 0
        result = await self._collection.update_many(
            {"requestedBy": user_id},
            {"$set": {"requestedBy": ANONYMOUS_USER_ID}},
        )
        return int(result.modified_count)

    async def delete_private_for_participant(self, user_id: str) -> int:
        """Borra análisis de partidas privadas en las que el usuario participó.

        Se usa el snapshot guardado al crear el análisis, no el estado actual de
        la partida, porque Game Logic puede haber anonimizado ya al usuario
        (sección 13).
        """
        result = await self._collection.delete_many(
            {"visibility": "private", "participantIds": user_id}
        )
        return int(result.deleted_count)
