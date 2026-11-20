"""Recuperación periódica de análisis perdidos (sección 17.4.1)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import Settings

LOGGER = logging.getLogger("analysis-worker.poller")

MAX_BATCH = 10
EXHAUSTED_ERROR = "El análisis alcanzó el límite de reclamos."


class AnalysisPoller:
    def __init__(
        self,
        repository: Any,
        processor: Any,
        settings: Settings,
        *,
        batch_limit: int = MAX_BATCH,
    ):
        self._repository = repository
        self._processor = processor
        self._settings = settings
        self._batch_limit = batch_limit

    async def run_once(self) -> int:
        """Recupera hasta 10 análisis. Devuelve cuántos intentó procesar."""
        try:
            candidates = await self._repository.find_recoverable(
                self._settings.stale_seconds, limit=self._batch_limit
            )
        except Exception:
            LOGGER.exception("No se pudo consultar los análisis recuperables")
            return 0

        processed = 0
        for candidate in candidates:
            analysis_id = candidate.get("analysisId")
            if not isinstance(analysis_id, str) or not analysis_id:
                continue
            try:
                document = await self._repository.get(analysis_id)
                if document is None:
                    continue

                claim_count = document.get("claimCount", 0)
                if not isinstance(claim_count, int) or isinstance(claim_count, bool):
                    claim_count = 0

                if claim_count >= self._settings.analysis_max_retries:
                    failed = await self._repository.fail_exhausted(
                        analysis_id,
                        self._settings.analysis_max_retries,
                        self._settings.stale_seconds,
                        EXHAUSTED_ERROR,
                    )
                    if failed:
                        LOGGER.error(
                            "Análisis %s pasado a failed: límite de reclamos",
                            analysis_id,
                        )
                    continue

                result = await self._processor.process(analysis_id)
                LOGGER.info(
                    "Recuperación de %s: %s", analysis_id, result
                )
                processed += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                # El lease vencerá y el siguiente ciclo lo recuperará.
                LOGGER.exception(
                    "Fallo recuperando el análisis %s", analysis_id
                )
        return processed

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self._settings.poll_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass
