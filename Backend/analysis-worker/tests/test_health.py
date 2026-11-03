"""Pruebas de GET /health, que solo depende de MongoDB (contrato, sección 17.2)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import create_app
from tests.conftest import FakeBroker, FakeEngine, FakeGameLogic, build_settings


class StubRepository:
    def __init__(self, *, healthy: bool = True, raise_error: bool = False):
        self._healthy = healthy
        self._raise_error = raise_error
        self.calls = 0

    async def healthy(self) -> bool:
        self.calls += 1
        if self._raise_error:
            raise RuntimeError("Mongo no responde")
        return self._healthy


def build_client(repository: StubRepository, broker: FakeBroker | None = None):
    app = create_app(
        build_settings(),
        repository=repository,
        game_logic=FakeGameLogic(),
        engine=FakeEngine(),
        broker=broker,
        start_background=False,
    )
    return TestClient(app)


def test_health_returns_ok_when_mongo_responds():
    repository = StubRepository(healthy=True)

    with build_client(repository) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert repository.calls == 1


def test_health_returns_503_when_mongo_is_down():
    repository = StubRepository(healthy=False)

    with build_client(repository) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICES_UNAVAILABLE"


def test_health_returns_503_when_mongo_raises():
    repository = StubRepository(raise_error=True)

    with build_client(repository) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICES_UNAVAILABLE"


def test_health_does_not_require_the_broker():
    broker = FakeBroker()
    repository = StubRepository(healthy=True)

    with build_client(repository, broker) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert broker.started == 0
    assert broker.closed == 0


def test_only_health_is_exposed():
    repository = StubRepository(healthy=True)

    with build_client(repository) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
