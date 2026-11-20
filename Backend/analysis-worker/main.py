"""Analysis Worker del Prototipo 2 (contrato, sección 17).

Arranque: ``uvicorn main:app --host 0.0.0.0 --port 8089``.

Solo expone ``GET /health``. Trabaja por dos vías complementarias:

* consume ``tutor.analysis.requested`` desde ``analysis-worker.requested``;
* cada ``POLL_INTERVAL_SECONDS`` recupera análisis perdidos por polling.

``/health`` depende solo de MongoDB, nunca del broker (sección 17.2).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.broker import RabbitMQBroker
from app.config import Settings
from app.consumer import AnalysisConsumer
from app.db import create_mongo_client
from app.engine import EngineClient
from app.game_logic import GameLogicClient
from app.messaging import MessageHandler
from app.poller import AnalysisPoller
from app.processor import AnalysisProcessor
from app.repository import AnalysisRepository

LOGGER = logging.getLogger("analysis-worker")


def _configure_logging(level: str) -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=getattr(logging, level, logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    root.setLevel(getattr(logging, level, logging.INFO))


def create_app(
    settings: Settings | None = None,
    *,
    repository: Any = None,
    game_logic: Any = None,
    engine: Any = None,
    broker: Any = None,
    start_background: bool = True,
) -> FastAPI:
    """Construye la aplicación con dependencias inyectables para las pruebas."""
    config = settings or Settings.from_env()
    _configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned: list[tuple[str, Any]] = []
        stop_event = asyncio.Event()
        tasks: list[asyncio.Task[Any]] = []

        current_repository = app.state.repository
        if current_repository is None:
            mongo_client = create_mongo_client(config.mongo_analysis_url)
            app.state.mongo_client = mongo_client
            current_repository = AnalysisRepository(
                mongo_client[config.mongo_analysis_database]
            )
            app.state.repository = current_repository
            owned.append(("mongo", mongo_client))

        current_game_logic = app.state.game_logic
        current_engine = app.state.engine
        if current_game_logic is None or current_engine is None:
            http_client = httpx.AsyncClient(
                base_url=config.gateway_internal_url,
                timeout=config.http_timeout,
            )
            app.state.http_client = http_client
            owned.append(("http", http_client))
            if current_game_logic is None:
                current_game_logic = GameLogicClient(http_client)
            if current_engine is None:
                current_engine = EngineClient(http_client)

        current_broker = app.state.broker
        if current_broker is None and start_background:
            current_broker = RabbitMQBroker(
                config.rabbitmq_url, timeout=config.http_timeout
            )
            app.state.broker = current_broker

        processor = AnalysisProcessor(
            current_repository, current_game_logic, current_engine, config
        )
        handler = MessageHandler(
            processor, maximum_depth=config.analysis_depth_max
        )
        poller = AnalysisPoller(current_repository, processor, config)

        app.state.processor = processor
        app.state.handler = handler
        app.state.poller = poller
        app.state.game_logic = current_game_logic
        app.state.engine = current_engine

        if start_background and current_broker is not None:
            consumer = AnalysisConsumer(
                current_broker, handler, retry_interval=config.poll_interval_seconds
            )
            app.state.consumer = consumer
            tasks.append(asyncio.create_task(poller.run(stop_event), name="poller"))
            tasks.append(asyncio.create_task(consumer.run(stop_event), name="consumer"))
            owned.append(("broker", current_broker))
        elif start_background:
            tasks.append(asyncio.create_task(poller.run(stop_event), name="poller"))

        LOGGER.info(
            "Analysis Worker listo (worker_id=%s, max_retries=%s, stale=%s min)",
            config.worker_id,
            config.analysis_max_retries,
            config.analysis_stale_minutes,
        )

        try:
            yield
        finally:
            stop_event.set()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            for kind, resource in reversed(owned):
                try:
                    if kind == "broker":
                        await resource.close()
                    elif kind == "http":
                        await resource.aclose()
                    elif kind == "mongo":
                        resource.close()
                except Exception:  # pragma: no cover - cierre best effort
                    LOGGER.exception("Error cerrando el recurso %s", kind)

    app = FastAPI(
        title="Analysis Worker",
        version="1.0.0",
        description="Cálculo de análisis de partidas terminadas.",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = config
    app.state.repository = repository
    app.state.game_logic = game_logic
    app.state.engine = engine
    app.state.broker = broker
    app.state.mongo_client = None
    app.state.http_client = None
    app.state.processor = None
    app.state.handler = None
    app.state.poller = None
    app.state.consumer = None

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception):
        LOGGER.exception("Error inesperado en el Analysis Worker", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Error interno del Analysis Worker.",
                }
            },
        )

    @app.get("/health", tags=["infra"])
    async def health(request: Request):
        current = request.app.state.repository
        try:
            healthy = current is not None and await current.healthy()
        except Exception:
            LOGGER.exception("La comprobación de salud de MongoDB falló")
            healthy = False
        if not healthy:
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "SERVICES_UNAVAILABLE",
                        "message": "La base de datos de análisis no está disponible.",
                    }
                },
            )
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = app.state.settings
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=False)
