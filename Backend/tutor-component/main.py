"""Servicio Tutor del Prototipo 2 (contrato, sección 16).

Arranque: ``uvicorn main:app --host 0.0.0.0 --port 8085``.

El servicio expone solo rutas internas ``/internal/tutor/*`` y ``GET /health``.
El gateway web publica ``/tutor/*`` y añade ``X-User-Id``.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.config import Settings
from app.db import create_mongo_client
from app.errors import ApiError
from app.events import EventPublisher
from app.game_logic import GameLogicClient
from app.repository import AnalysisRepository
from app.routes import router
from app.service import TutorService

LOGGER = logging.getLogger("tutor")


def _configure_logging(level: str) -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=getattr(logging, level, logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    root.setLevel(getattr(logging, level, logging.INFO))


async def _prepare_indexes(
    repository: AnalysisRepository, attempts: int = 5, delay: float = 1.0
) -> bool:
    """Crea los índices reintentando mientras Mongo termina de arrancar.

    Si no se consigue, el servicio sigue funcionando: la comprobación previa al
    insert cubre los duplicados salvo en peticiones simultáneas. El índice
    único es obligatorio para la idempotencia estricta del contrato y /health
    lo verifica en cada llamada.
    """
    for attempt in range(1, attempts + 1):
        try:
            await repository.ensure_indexes()
            LOGGER.info("Índices de la base de análisis listos")
            return True
        except Exception as exc:  # depende de la red y del estado de Mongo
            if attempt == attempts:
                LOGGER.error(
                    "No se pudieron crear los índices de análisis tras %s intentos: %s",
                    attempts,
                    exc,
                )
                return False
            LOGGER.warning(
                "MongoDB de análisis no está listo para crear índices "
                "(intento %s/%s)",
                attempt,
                attempts,
            )
            await asyncio.sleep(delay)
    return False


def create_app(
    settings: Settings | None = None,
    *,
    repository: Any = None,
    game_logic: Any = None,
    publisher: Any = None,
) -> FastAPI:
    """Construye la aplicación.

    Los parámetros opcionales permiten inyectar dobles en las pruebas sin
    abrir conexiones a MongoDB ni a RabbitMQ.
    """
    config = settings or Settings.from_env()
    _configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned: list[tuple[str, Any]] = []

        current_repository = app.state.repository
        if current_repository is None:
            mongo_client = create_mongo_client(config.mongo_analysis_url)
            app.state.mongo_client = mongo_client
            current_repository = AnalysisRepository(
                mongo_client[config.mongo_analysis_database]
            )
            app.state.repository = current_repository
            owned.append(("mongo", mongo_client))
            await _prepare_indexes(current_repository)

        current_game_logic = app.state.game_logic
        if current_game_logic is None:
            http_client = httpx.AsyncClient(
                base_url=config.gateway_internal_url,
                timeout=config.http_timeout,
            )
            current_game_logic = GameLogicClient(http_client)
            app.state.game_logic = current_game_logic
            app.state.http_client = http_client
            owned.append(("http", http_client))

        current_publisher = app.state.publisher
        if current_publisher is None:
            current_publisher = EventPublisher(
                config.rabbitmq_url,
                exchange=config.exchange,
                routing_key=config.routing_key,
                timeout=config.rabbitmq_timeout,
            )
            app.state.publisher = current_publisher
            owned.append(("publisher", current_publisher))
            await current_publisher.start()

        app.state.service = TutorService(
            config, current_repository, current_game_logic, current_publisher
        )
        LOGGER.info(
            "Tutor listo (engineVersion=%s, depth=%s..%s)",
            config.engine_version,
            config.analysis_depth_default,
            config.analysis_depth_max,
        )

        try:
            yield
        finally:
            for kind, resource in reversed(owned):
                try:
                    if kind == "publisher":
                        await resource.close()
                    elif kind == "http":
                        await resource.aclose()
                    elif kind == "mongo":
                        resource.close()
                except Exception:  # pragma: no cover - cierre best effort
                    LOGGER.exception("Error cerrando el recurso %s", kind)

    app = FastAPI(
        title="Tutor",
        version="1.0.0",
        description="Solicitudes de análisis, informes y borrado de cuenta.",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.repository = repository
    app.state.game_logic = game_logic
    app.state.publisher = publisher
    app.state.mongo_client = None
    app.state.http_client = None
    app.state.service = None

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code, content=exc.payload())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _exc: RequestValidationError
    ):
        # El formato del contrato exige VALIDATION_ERROR también para cuerpos
        # que no cumplen el esquema de Pydantic (sección 20).
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "La solicitud no cumple el formato esperado.",
                }
            },
        )

    @app.exception_handler(PyMongoError)
    async def mongo_error_handler(_request: Request, exc: PyMongoError):
        # El servicio depende de la base de análisis: si no responde, el
        # llamador recibe el 503 del contrato (sección 20).
        LOGGER.exception("MongoDB de análisis no respondió", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "SERVICES_UNAVAILABLE",
                    "message": "La base de datos de análisis no está disponible.",
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception):
        LOGGER.exception("Error inesperado en el Tutor", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Error interno del Tutor.",
                }
            },
        )

    app.include_router(router)

    @app.get("/health", tags=["infra"])
    async def health(request: Request):
        current = request.app.state.repository
        if current is None or not await current.healthy():
            raise ApiError(
                503,
                "SERVICES_UNAVAILABLE",
                "La base de datos de análisis no está disponible.",
            )
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = app.state.settings
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=False)
