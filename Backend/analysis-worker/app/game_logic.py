"""Cliente de ``GET /internal/logic/games/{id}/analysis-input`` (sección 11.4)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.errors import AnalysisFailure
from app.http_utils import error_code

LOGGER = logging.getLogger("analysis-worker.game_logic")


class GameLogicClient:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def get_analysis_input(self, game_id: str) -> dict[str, Any]:
        path = f"/internal/logic/games/{game_id}/analysis-input"
        try:
            response = await self._client.get(path)
        except httpx.TimeoutException as exc:
            LOGGER.warning("Game Logic agotó el tiempo al pedir %s", path)
            raise AnalysisFailure(
                "Game Logic no respondió a tiempo.",
                failure_kind="transient",
                code="SERVICES_UNAVAILABLE",
            ) from exc
        except httpx.RequestError as exc:
            LOGGER.warning("Game Logic no respondió al pedir %s: %s", path, exc)
            raise AnalysisFailure(
                "Game Logic no está disponible en este momento.",
                failure_kind="transient",
                code="SERVICES_UNAVAILABLE",
            ) from exc

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise AnalysisFailure(
                    "Game Logic devolvió una respuesta que no es JSON.",
                    failure_kind="permanent",
                ) from exc
            if not isinstance(payload, dict):
                raise AnalysisFailure(
                    "Game Logic devolvió un análisis de entrada inválido.",
                    failure_kind="permanent",
                )
            return payload

        code = error_code(response)
        if response.status_code >= 500:
            raise AnalysisFailure(
                "Game Logic no pudo entregar los datos de la partida.",
                failure_kind="transient",
                code=code or "SERVICES_UNAVAILABLE",
            )

        # 404 y 409 son definitivos según la tabla de fallos del contrato.
        raise AnalysisFailure(
            "Game Logic rechazó los datos de la partida.",
            failure_kind="permanent",
            code=code,
        )
