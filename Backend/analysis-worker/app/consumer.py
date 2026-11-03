"""Bucle de consumo con reconexión a RabbitMQ."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

LOGGER = logging.getLogger("analysis-worker.consumer")


class AnalysisConsumer:
    def __init__(self, broker: Any, handler: Any, retry_interval: float = 5.0):
        self._broker = broker
        self._handler = handler
        self._retry_interval = retry_interval

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await self._broker.start()
                await self._broker.consume(self._handler.handle)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception(
                    "RabbitMQ no está disponible; se reintentará la conexión"
                )
            finally:
                try:
                    await self._broker.close()
                except Exception:  # pragma: no cover - cierre best effort
                    LOGGER.exception("Error cerrando RabbitMQ")

            if stop_event.is_set():
                return
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=self._retry_interval
                )
            except asyncio.TimeoutError:
                pass
