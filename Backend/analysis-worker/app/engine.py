"""Cliente de ``POST /internal/engine-analysis/evaluate`` (sección 15.4)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.errors import AnalysisFailure
from app.http_utils import error_code

LOGGER = logging.getLogger("analysis-worker.engine")


class EngineClient:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def evaluate(self, fen: str, depth: int) -> dict[str, Any]:
        try:
            response = await self._client.post(
                "/internal/engine-analysis/evaluate",
                json={"fen": fen, "depth": depth},
            )
        except httpx.TimeoutException as exc:
            raise AnalysisFailure(
                "El motor de análisis no respondió a tiempo.",
                failure_kind="transient",
                code="ENGINE_TIMEOUT",
            ) from exc
        except httpx.RequestError as exc:
            raise AnalysisFailure(
                "El motor de análisis no está disponible.",
                failure_kind="transient",
                code="SERVICES_UNAVAILABLE",
            ) from exc

        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise AnalysisFailure(
                    "Botcito-análisis devolvió una respuesta que no es JSON.",
                    failure_kind="permanent",
                ) from exc
            if not isinstance(payload, dict):
                raise AnalysisFailure(
                    "Botcito-análisis devolvió una respuesta inválida.",
                    failure_kind="permanent",
                )
            return payload

        code = error_code(response)
        if response.status_code >= 500:
            if code is None and response.status_code == 504:
                code = "ENGINE_TIMEOUT"
            if code is None and response.status_code == 503:
                code = "SERVICES_UNAVAILABLE"
            raise AnalysisFailure(
                "El motor de análisis no pudo evaluar la posición.",
                failure_kind="transient",
                code=code,
            )

        # 400 VALIDATION_ERROR/INVALID_FEN y cualquier otro 4xx indican datos
        # inconsistentes: reintentar no los arregla.
        fail_code = code or "VALIDATION_ERROR"
        LOGGER.warning(
            "Botcito-análisis rechazó la posición con %s (%s)",
            response.status_code,
            fail_code,
        )
        raise AnalysisFailure(
            "Botcito-análisis rechazó la posición enviada.",
            failure_kind="permanent",
            code=fail_code,
        )
