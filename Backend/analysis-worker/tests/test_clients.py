"""Pruebas de los clientes HTTP internos y su clasificación de fallos."""

from __future__ import annotations

import httpx
import pytest

from app.engine import EngineClient
from app.errors import AnalysisFailure
from app.game_logic import GameLogicClient
from tests.conftest import evaluation_payload, make_game_input, new_uuid


def client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://gateway.test",
    )


async def test_game_logic_returns_analysis_input():
    game_id = new_uuid()
    payload = make_game_input(game_id)

    async with client_with(
        lambda request: httpx.Response(200, json=payload)
    ) as client:
        result = await GameLogicClient(client).get_analysis_input(game_id)

    assert result["gameId"] == game_id


async def test_game_logic_404_is_permanent():
    async with client_with(
        lambda request: httpx.Response(
            404, json={"error": {"code": "GAME_NOT_FOUND", "message": "no"}}
        )
    ) as client:
        with pytest.raises(AnalysisFailure) as captured:
            await GameLogicClient(client).get_analysis_input(new_uuid())

    assert captured.value.failure_kind == "permanent"
    assert captured.value.code == "GAME_NOT_FOUND"


async def test_game_logic_5xx_is_transient():
    async with client_with(
        lambda request: httpx.Response(
            503,
            json={"error": {"code": "SERVICES_UNAVAILABLE", "message": "no"}},
        )
    ) as client:
        with pytest.raises(AnalysisFailure) as captured:
            await GameLogicClient(client).get_analysis_input(new_uuid())

    assert captured.value.failure_kind == "transient"


async def test_game_logic_network_error_is_transient():
    def handler(request: httpx.Request):
        raise httpx.ConnectError("sin conexión", request=request)

    async with client_with(handler) as client:
        with pytest.raises(AnalysisFailure) as captured:
            await GameLogicClient(client).get_analysis_input(new_uuid())

    assert captured.value.failure_kind == "transient"


async def test_game_logic_invalid_json_is_permanent():
    async with client_with(
        lambda request: httpx.Response(200, text="no-json")
    ) as client:
        with pytest.raises(AnalysisFailure) as captured:
            await GameLogicClient(client).get_analysis_input(new_uuid())

    assert captured.value.failure_kind == "permanent"


async def test_engine_returns_evaluation():
    async with client_with(
        lambda request: httpx.Response(200, json=evaluation_payload(25, best_uci="e2e4"))
    ) as client:
        result = await EngineClient(client).evaluate("fen", 15)

    assert result["evaluation"]["value"] == 25


async def test_engine_504_is_transient():
    async with client_with(
        lambda request: httpx.Response(504, json={})
    ) as client:
        with pytest.raises(AnalysisFailure) as captured:
            await EngineClient(client).evaluate("fen", 15)

    assert captured.value.failure_kind == "transient"
    assert captured.value.code == "ENGINE_TIMEOUT"


async def test_engine_busy_is_transient_with_code():
    async with client_with(
        lambda request: httpx.Response(
            503, json={"error": {"code": "ENGINE_BUSY", "message": "ocupado"}}
        )
    ) as client:
        with pytest.raises(AnalysisFailure) as captured:
            await EngineClient(client).evaluate("fen", 15)

    assert captured.value.failure_kind == "transient"
    assert captured.value.code == "ENGINE_BUSY"


async def test_engine_400_is_permanent():
    async with client_with(
        lambda request: httpx.Response(
            400, json={"error": {"code": "INVALID_FEN", "message": "mala"}}
        )
    ) as client:
        with pytest.raises(AnalysisFailure) as captured:
            await EngineClient(client).evaluate("fen", 15)

    assert captured.value.failure_kind == "permanent"
    assert captured.value.code == "INVALID_FEN"


async def test_engine_invalid_json_is_permanent():
    async with client_with(
        lambda request: httpx.Response(200, text="no-json")
    ) as client:
        with pytest.raises(AnalysisFailure) as captured:
            await EngineClient(client).evaluate("fen", 15)

    assert captured.value.failure_kind == "permanent"


async def test_engine_timeout_is_transient():
    def handler(request: httpx.Request):
        raise httpx.ReadTimeout("timeout", request=request)

    async with client_with(handler) as client:
        with pytest.raises(AnalysisFailure) as captured:
            await EngineClient(client).evaluate("fen", 15)

    assert captured.value.failure_kind == "transient"
    assert captured.value.code == "ENGINE_TIMEOUT"
