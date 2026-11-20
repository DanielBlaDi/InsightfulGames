"""Orquestación de un análisis (contrato, secciones 17.2 y 17.4)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from app.calculation import compute_result, normalize_evaluation, parse_game_input
from app.config import RETRY_DELAYS_SECONDS, Settings
from app.errors import AnalysisFailure, LeaseLostError
from app.models import Evaluation

LOGGER = logging.getLogger("analysis-worker.processor")

OUTCOME_COMPLETED = "completed"
OUTCOME_FAILED_TRANSIENT = "failed_transient"
OUTCOME_FAILED_PERMANENT = "failed_permanent"
OUTCOME_SKIPPED = "skipped"
OUTCOME_DISCARDED = "discarded"
OUTCOME_LEASE_LOST = "lease_lost"

SleepFunction = Callable[[float], Awaitable[None]]


class AnalysisProcessor:
    def __init__(
        self,
        repository: Any,
        game_logic: Any,
        engine: Any,
        settings: Settings,
        *,
        retry_sleep: SleepFunction = asyncio.sleep,
    ):
        self._repository = repository
        self._game_logic = game_logic
        self._engine = engine
        self._settings = settings
        self._retry_sleep = retry_sleep
        # Un análisis a la vez por proceso (contrato, sección 17.2). El
        # consumidor y el poller comparten esta instancia.
        self._lock = asyncio.Lock()

    async def process(self, analysis_id: str) -> str:
        """Reclama y procesa un análisis. Devuelve el desenlace del intento.

        Un resultado ``skipped`` significa que otro worker lo tiene o que ya no
        está pendiente: el mensaje se confirma sin trabajo.
        """
        async with self._lock:
            return await self._process_one(analysis_id)

    async def _process_one(self, analysis_id: str) -> str:
        document = await self._repository.claim(
            analysis_id,
            self._settings.worker_id,
            self._settings.stale_seconds,
            self._settings.analysis_max_retries,
        )
        if document is None:
            return OUTCOME_SKIPPED

        lost = asyncio.Event()
        renew_task = asyncio.create_task(
            self._renew_loop(analysis_id, lost), name=f"lease-{analysis_id}"
        )
        try:
            return await self._process_claimed(document, lost)
        except LeaseLostError:
            LOGGER.warning(
                "Análisis %s: el worker perdió el lease y descarta su trabajo",
                analysis_id,
            )
            return OUTCOME_LEASE_LOST
        finally:
            renew_task.cancel()
            try:
                await renew_task
            except asyncio.CancelledError:
                pass
            except Exception:  # pragma: no cover - la tarea solo registra
                LOGGER.exception(
                    "Análisis %s: error cerrando la renovación del lease",
                    analysis_id,
                )

    async def _renew_loop(self, analysis_id: str, lost: asyncio.Event) -> None:
        interval = self._settings.renewal_interval_seconds
        while not lost.is_set():
            await asyncio.sleep(interval)
            if lost.is_set():
                return
            try:
                renewed = await self._repository.renew(
                    analysis_id,
                    self._settings.worker_id,
                    self._settings.stale_seconds,
                )
            except Exception:
                # Sin renovación fiable se aborta para no escribir con un lease
                # que puede haber sido reclamado por otro worker.
                LOGGER.exception(
                    "Análisis %s: no se pudo renovar el lease", analysis_id
                )
                lost.set()
                return
            if not renewed:
                LOGGER.warning(
                    "Análisis %s: el lease ya no pertenece a este worker",
                    analysis_id,
                )
                lost.set()
                return

    async def _process_claimed(
        self, document: dict[str, Any], lost: asyncio.Event
    ) -> str:
        analysis_id = document.get("analysisId")
        game_id = document.get("gameId")
        depth = document.get("depth")

        if not isinstance(analysis_id, str) or not analysis_id:
            # Un documento sin analysisId no debería existir; no hay nada que
            # escribir de forma segura.
            LOGGER.error("El documento reclamado no tiene analysisId")
            return OUTCOME_LEASE_LOST
        if not isinstance(game_id, str) or not game_id:
            return await self._finish_failed(
                analysis_id,
                lost,
                AnalysisFailure(
                    "El análisis no tiene una partida asociada.",
                    failure_kind="permanent",
                ),
            )
        if (
            isinstance(depth, bool)
            or not isinstance(depth, int)
            or not 1 <= depth <= self._settings.analysis_depth_max
        ):
            return await self._finish_failed(
                analysis_id,
                lost,
                AnalysisFailure(
                    "El análisis tiene una profundidad inválida.",
                    failure_kind="permanent",
                ),
            )

        try:
            data = await self._game_logic.get_analysis_input(game_id)
            self._ensure_lease(lost)
            game = parse_game_input(data, game_id)
        except AnalysisFailure as exc:
            return await self._finish_failed(analysis_id, lost, exc)

        evaluations: list[Evaluation] = []
        for index, (fen, terminal_mate) in enumerate(
            zip(game.positions, game.terminal_mate)
        ):
            self._ensure_lease(lost)
            try:
                payload = await self._evaluate_with_retries(fen, depth, lost)
                self._ensure_lease(lost)
                evaluations.append(
                    normalize_evaluation(payload, terminal_mate=terminal_mate)
                )
            except AnalysisFailure as exc:
                LOGGER.warning(
                    "Análisis %s: fallo en la posición %s/%s (%s): %s",
                    analysis_id,
                    index + 1,
                    len(game.positions),
                    exc.failure_kind,
                    exc.message,
                )
                return await self._finish_failed(analysis_id, lost, exc)

        try:
            result = compute_result(
                game,
                evaluations,
                inaccuracy_cp=self._settings.analysis_inaccuracy_cp,
                mistake_cp=self._settings.analysis_mistake_cp,
                blunder_cp=self._settings.analysis_blunder_cp,
            )
        except AnalysisFailure as exc:
            return await self._finish_failed(analysis_id, lost, exc)

        self._ensure_lease(lost)
        written = await self._repository.finalize_completed(
            analysis_id, self._settings.worker_id, result
        )
        if not written:
            LOGGER.warning(
                "Análisis %s: el resultado se descarta porque el lease venció "
                "o el documento ya no existe",
                analysis_id,
            )
            return OUTCOME_LEASE_LOST if lost.is_set() else OUTCOME_DISCARDED

        LOGGER.info(
            "Análisis %s completado (%s posiciones)", analysis_id, len(evaluations)
        )
        return OUTCOME_COMPLETED

    async def _evaluate_with_retries(
        self, fen: str, depth: int, lost: asyncio.Event
    ) -> dict[str, Any]:
        attempts = max(1, self._settings.analysis_max_retries)
        last_error: AnalysisFailure | None = None

        for attempt in range(1, attempts + 1):
            self._ensure_lease(lost)
            try:
                return await self._engine.evaluate(fen, depth)
            except AnalysisFailure as exc:
                if not exc.transient:
                    raise
                last_error = exc
                if attempt >= attempts:
                    break
                delay = RETRY_DELAYS_SECONDS[
                    min(attempt - 1, len(RETRY_DELAYS_SECONDS) - 1)
                ]
                LOGGER.warning(
                    "Evaluación transitoria fallida (intento %s/%s): %s; "
                    "reintento en %ss",
                    attempt,
                    attempts,
                    exc.message,
                    delay,
                )
                await self._retry_sleep(delay)
                self._ensure_lease(lost)

        if last_error is not None:
            raise last_error
        raise AnalysisFailure(
            "El motor de análisis no respondió.",
            failure_kind="transient",
            code="ENGINE_TIMEOUT",
        )

    async def _finish_failed(
        self,
        analysis_id: str,
        lost: asyncio.Event,
        failure: AnalysisFailure,
    ) -> str:
        if lost.is_set():
            return OUTCOME_LEASE_LOST

        written = await self._repository.finalize_failed(
            analysis_id,
            self._settings.worker_id,
            failure.failure_kind,
            failure.message,
        )
        if not written:
            LOGGER.warning(
                "Análisis %s: no se pudo marcar failed porque el lease venció "
                "o el documento ya no existe",
                analysis_id,
            )
            return OUTCOME_LEASE_LOST if lost.is_set() else OUTCOME_DISCARDED

        LOGGER.warning(
            "Análisis %s marcado failed (%s): %s",
            analysis_id,
            failure.failure_kind,
            failure.message,
        )
        return (
            OUTCOME_FAILED_TRANSIENT
            if failure.failure_kind == "transient"
            else OUTCOME_FAILED_PERMANENT
        )

    @staticmethod
    def _ensure_lease(lost: asyncio.Event) -> None:
        if lost.is_set():
            raise LeaseLostError()
