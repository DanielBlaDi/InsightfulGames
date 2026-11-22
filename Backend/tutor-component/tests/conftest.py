"""Fixtures del Tutor: Mongo en memoria y RabbitMQ simulado (el Tutor ya no llama a Game Logic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.config import Settings
from app.repository import AnalysisRepository
from main import create_app


class FakePublisher:
    """Sustituye la publicación en RabbitMQ."""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self.accepting = True

    async def publish_analysis_requested(self, analysis: dict) -> bool:
        if not self.accepting:
            return False
        self.published.append(dict(analysis))
        return True


def build_settings(**overrides) -> Settings:
    values = dict(
        port=8085,
        mongo_analysis_url="mongodb://unused",
        mongo_analysis_database="tutor_test",
        rabbitmq_url="amqp://unused",
        engine_version="stockfish-15.1",
        analysis_depth_default=15,
        analysis_depth_max=18,
        analysis_max_reactivations=3,
        llm_provider="mock",
        http_timeout=5.0,
        log_level="WARNING",
    )
    values.update(overrides)
    return Settings(**values)


@dataclass
class Harness:
    app: Any
    http: httpx.AsyncClient
    repository: AnalysisRepository
    publisher: FakePublisher
    settings: Settings


@pytest_asyncio.fixture
async def tutor():
    mongo = AsyncMongoMockClient()
    repository = AnalysisRepository(mongo["tutor_test"])
    await repository.ensure_indexes()

    publisher = FakePublisher()
    settings = build_settings()
    app = create_app(settings, repository=repository, publisher=publisher)

    # Sin bases ni broker reales: se entra al lifespan para construir el servicio.
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://tutor"
        ) as http:
            yield Harness(
                app=app,
                http=http,
                repository=repository,
                publisher=publisher,
                settings=settings,
            )
