"""Lógica del Tutor (contrato v9, sección 13).

Responsabilidades:
- validar que la partida exista, esté terminada y sea visible;
- crear el análisis una sola vez por (gameId, engineVersion, language,
  detailLevel, depth), publicar el evento y responder 202/200;
- verificar la visibilidad en cada lectura;
- entregar el informe y generar la explicación mock;
- atender el borrado de cuenta de forma idempotente.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.config import ANONYMOUS_USER_ID, Settings
from app.errors import ApiError
from app.explanation import build_explanation
from app.game_logic import is_visible, participant_ids, visibility_snapshot
from app.models import AnalysisRequest, result_parts, status_payload
from app.repository import AnalysisRepository
from app.timeutils import to_iso, utcnow
from app.validation import normalize_depth, normalize_text, normalize_uuid

LOGGER = logging.getLogger("tutor.service")


class TutorService:
    def __init__(
        self,
        settings: Settings,
        repository: AnalysisRepository,
        game_logic: Any,
        publisher: Any,
    ):
        self._settings = settings
        self._repository = repository
        self._game_logic = game_logic
        self._publisher = publisher

    # ------------------------------------------------------------------ POST
    async def request_analysis(
        self, request: AnalysisRequest, user_id: str
    ) -> tuple[dict[str, Any], bool]:
        """Crea o recupera el análisis. Devuelve (vista, creado)."""
        game_id = normalize_uuid(request.gameId, "gameId")
        depth = normalize_depth(
            request.depth,
            self._settings.analysis_depth_default,
            self._settings.analysis_depth_max,
        )
        language = normalize_text(request.language, "language", 16)
        detail_level = normalize_text(request.detailLevel, "detailLevel", 32)

        game = await self._game_logic.get_game(game_id)
        if not is_visible(game, user_id):
            # El contrato no distingue "no existe" de "no visible" (sección 13).
            raise ApiError(
                404,
                "GAME_NOT_FOUND",
                "La partida no existe o no es visible para el usuario.",
            )
        if game.get("status") != "finished":
            raise ApiError(
                409,
                "GAME_NOT_FINISHED",
                "La partida debe estar terminada para pedir su análisis.",
            )

        engine_version = self._settings.engine_version
        existing = await self._repository.find_by_key(
            game_id, engine_version, language, detail_level, depth
        )
        if existing is not None:
            return status_payload(existing), False

        now = utcnow()
        analysis_id = str(uuid.uuid4())
        document: dict[str, Any] = {
            "_id": analysis_id,
            "analysisId": analysis_id,
            "gameId": game_id,
            "engineVersion": engine_version,
            "language": language,
            "detailLevel": detail_level,
            "depth": depth,
            "status": "pending",
            "requestedBy": user_id,
            # Snapshot para el borrado de cuenta; la visibilidad de lectura se
            # consulta siempre a Game Logic (sección 13).
            "participantIds": participant_ids(game),
            "visibility": visibility_snapshot(game),
            "result": None,
            "error": None,
            "explanation": None,
            "createdAt": now,
            "updatedAt": now,
            "startedAt": None,
            "completedAt": None,
        }

        created = await self._repository.insert(document)
        if not created:
            # Otro POST simultáneo ganó la carrera del índice único: se devuelve
            # el análisis que ya existe, igual que en la ruta de "ya existe".
            existing = await self._repository.find_by_key(
                game_id, engine_version, language, detail_level, depth
            )
            if existing is not None:
                return status_payload(existing), False
            raise ApiError(
                503,
                "SERVICES_UNAVAILABLE",
                "No se pudo registrar el análisis.",
            )

        published = await self._publisher.publish_analysis_requested(document)
        if not published:
            LOGGER.warning(
                "Análisis %s guardado en pending sin evento publicado; "
                "el polling del Analysis Worker lo recuperará.",
                analysis_id,
            )
        return status_payload(document), True

    # --------------------------------------------------------------- GETs
    async def get_analysis(self, analysis_id: str, user_id: str) -> dict[str, Any]:
        document = await self._load_visible(analysis_id, user_id)
        return status_payload(document)

    async def get_result(self, analysis_id: str, user_id: str) -> dict[str, Any]:
        document = await self._load_visible(analysis_id, user_id)

        status = document.get("status")
        if status != "completed":
            raise ApiError(
                409,
                "ANALYSIS_NOT_READY",
                f"El análisis todavía no está listo (estado: {status}).",
            )

        parts = result_parts(document)
        if parts is None:
            LOGGER.error(
                "El análisis %s está completed pero no tiene summary ni moves",
                document.get("analysisId"),
            )
            raise ApiError(
                409,
                "ANALYSIS_NOT_READY",
                "El análisis todavía no tiene un resultado disponible.",
            )
        summary, moves = parts

        language = document.get("language") or "es"
        explanation = document.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip():
            explanation = build_explanation(
                summary,
                language=language,
                detail_level=document.get("detailLevel") or "standard",
            )
            await self._repository.save_explanation(
                document["analysisId"], explanation
            )

        return {
            "analysisId": document["analysisId"],
            "gameId": document["gameId"],
            "engineVersion": document.get("engineVersion"),
            "depth": document.get("depth"),
            "language": language,
            "detailLevel": document.get("detailLevel"),
            "summary": summary,
            "moves": moves,
            "explanation": explanation,
            "createdAt": to_iso(document.get("createdAt")),
        }

    async def _load_visible(
        self, analysis_id: str, user_id: str
    ) -> dict[str, Any]:
        document = await self._repository.get(analysis_id)
        if document is None:
            raise ApiError(
                404,
                "ANALYSIS_NOT_FOUND",
                "El análisis no existe o no es visible para el usuario.",
            )

        try:
            game = await self._game_logic.get_game(document["gameId"])
        except ApiError as exc:
            if exc.code == "GAME_NOT_FOUND":
                # La partida desapareció o dejó de ser visible: para el usuario
                # el análisis tampoco existe (sección 13).
                raise ApiError(
                    404,
                    "ANALYSIS_NOT_FOUND",
                    "El análisis no existe o no es visible para el usuario.",
                ) from exc
            raise

        if not is_visible(game, user_id):
            raise ApiError(
                404,
                "ANALYSIS_NOT_FOUND",
                "El análisis no existe o no es visible para el usuario.",
            )
        return document

    # -------------------------------------------------------------- DELETE
    async def delete_user(self, user_id: str) -> None:
        """Borrado de cuenta: anonimiza y elimina lo privado. Idempotente."""
        normalized = normalize_uuid(user_id, "userId")
        if normalized == ANONYMOUS_USER_ID:
            return

        anonymized = await self._repository.anonymize_requested_by(normalized)
        deleted = await self._repository.delete_private_for_participant(normalized)
        LOGGER.info(
            "Borrado del usuario %s en Tutor: %s análisis anonimizados, %s eliminados",
            normalized,
            anonymized,
            deleted,
        )
