"""Fixtures del Tutor: Mongo en memoria, Game Logic y RabbitMQ simulados."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.config import Settings
from app.errors import ApiError
from app.repository import AnalysisRepository
from main import create_app


class FakeGameLogic:
    """Sustituye a GET /internal/logic/games/{id}."""

    def __init__(self) -> None:
        self.games: dict[str, dict] = {}
        self.down = False
        self.failing_ids: set[str] = set()

    def add(self, game: dict) -> None:
        self.games[game["gameId"]] = game

    def remove(self, game_id: str) -> None:
        self.games.pop(game_id, None)

    async def get_game(self, game_id: str) -> dict:
        if self.down or game_id in self.failing_ids:
            raise ApiError(
                503, "SERVICES_UNAVAILABLE", "Game Logic no está disponible."
            )
        game = self.games.get(game_id)
        if game is None:
            raise ApiError(404, "GAME_NOT_FOUND", "La partida no existe.")
        return dict(game)


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
        gateway_internal_url="http://gateway.test",
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
    logic: FakeGameLogic
    publisher: FakePublisher
    settings: Settings


@pytest_asyncio.fixture
async def tutor():
    mongo = AsyncMongoMockClient()
    repository = AnalysisRepository(mongo["tutor_test"])
    await repository.ensure_indexes()

    logic = FakeGameLogic()
    publisher = FakePublisher()
    settings = build_settings()
    app = create_app(
        settings,
        repository=repository,
        game_logic=logic,
        publisher=publisher,
    )

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
                logic=logic,
                publisher=publisher,
                settings=settings,
            )
