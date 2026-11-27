"""Repositorio de la colección ``analyses`` (MongoDB de análisis)."""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.config import ANONYMOUS_USER_ID
from app.timeutils import utcnow

LOGGER = logging.getLogger("tutor.repository")

COLLECTION_NAME = "analyses"

# Clave de análisis del contrato (sección 16.4): (gameId, engineVersion,
# language, detailLevel, depth).
KEY_FIELDS = ("gameId", "engineVersion", "language", "detailLevel", "depth")
UNIQUE_INDEX_NAME = "uq_analyses_key"
REQUESTED_BY_INDEX_NAME = "ix_analyses_requested_by_created"
PARTICIPANT_INDEX_NAME = "ix_analyses_participant_ids"


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
        simultáneos con la misma clave (sección 16.4). El nombre es explícito
        para que un cambio de clave falle de forma visible.
        """
        await self._collection.create_index(
            [(field, 1) for field in KEY_FIELDS],
            unique=True,
            name=UNIQUE_INDEX_NAME,
        )
        await self._collection.create_index(
            [("requestedBy", 1), ("createdAt", -1)],
            name=REQUESTED_BY_INDEX_NAME,
        )
        await self._collection.create_index(
            [("participantIds", 1)],
            name=PARTICIPANT_INDEX_NAME,
        )

    async def healthy(self) -> bool:
        """Comprueba Mongo y que el índice único esté realmente creado.

        Sin ``uq_analyses_key`` el servicio sigue aceptando escrituras, pero
        pierde la protección de idempotencia. ``/health`` debe reflejarlo
        (sección 16.3).
        """
        try:
            indexes = await self._collection.index_information()
        except Exception:  # pragma: no cover - depende de la red/Mongo
            LOGGER.exception("MongoDB de análisis no responde")
            return False

        info = indexes.get(UNIQUE_INDEX_NAME)
        if not isinstance(info, dict) or not info.get("unique"):
            LOGGER.error("Falta el índice único %s", UNIQUE_INDEX_NAME)
            return False

        key = info.get("key")
        fields = tuple(name for name, _direction in key) if key else ()
        if fields != KEY_FIELDS:
            LOGGER.error(
                "El índice %s no cubre la clave esperada: %s",
                UNIQUE_INDEX_NAME,
                fields,
            )
            return False
        return True

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

    async def reactivate(
        self, analysis_id: str, max_reactivations: int
    ) -> bool:
        """Reactiva atómicamente un fallo transitorio (sección 16.4.3).

        La condición incluye el estado, el tipo de fallo y el número de
        reactivaciones, de modo que dos POST simultáneos solo reactivan una vez.
        Conserva ``analysisId`` y la clave del análisis.
        """
        result = await self._collection.update_one(
            {
                "analysisId": analysis_id,
                "status": "failed",
                "failureKind": "transient",
                "reactivations": {"$lt": max_reactivations},
            },
            {
                "$set": {
                    "status": "pending",
                    "error": None,
                    "updatedAt": utcnow(),
                },
                "$unset": {
                    "failureKind": "",
                    "leaseUntil": "",
                    "leaseOwner": "",
                    "claimCount": "",
                },
                "$inc": {"reactivations": 1},
            },
        )
        return result.modified_count == 1

    async def game_ids_for_participant(self, user_id: str) -> list[str]:
        """Partidas distintas con análisis en los que participó el usuario."""
        game_ids = await self._collection.distinct(
            "gameId", {"participantIds": user_id}
        )
        return [game_id for game_id in game_ids if isinstance(game_id, str)]

    async def delete_by_game(self, game_id: str) -> int:
        """Borra todos los análisis de una partida (sección 16.4.4)."""
        result = await self._collection.delete_many({"gameId": game_id})
        return int(result.deleted_count)

    async def anonymize_participant(self, user_id: str) -> int:
        """Reemplaza el userId por el anónimo en ``participantIds``.

        Se hace lectura-modificación-escritura porque ``arrayFilters`` no está
        disponible en mongomock. La operación es idempotente y deduplica el
        array, ya que el anónimo puede coincidir con otra entrada.
        """
        if user_id == ANONYMOUS_USER_ID:
            return 0

        modified = 0
        cursor = self._collection.find({"participantIds": user_id})
        async for document in cursor:
            participants = document.get("participantIds")
            if not isinstance(participants, list):
                continue

            anonymized: list[Any] = []
            for participant in participants:
                value = (
                    ANONYMOUS_USER_ID if participant == user_id else participant
                )
                if value not in anonymized:
                    anonymized.append(value)

            if anonymized == participants:
                continue

            result = await self._collection.update_one(
                {"_id": document["_id"]},
                {"$set": {"participantIds": anonymized}},
            )
            modified += int(result.modified_count)
        return modified

    async def anonymize_requested_by(self, user_id: str) -> int:
        """Reemplaza requestedBy por el valor anónimo (borrado de cuenta)."""
        if user_id == ANONYMOUS_USER_ID:
            return 0
        result = await self._collection.update_many(
            {"requestedBy": user_id},
            {"$set": {"requestedBy": ANONYMOUS_USER_ID}},
        )
        return int(result.modified_count)
