"""Pruebas del contrato HTTP usando un proceso Stockfish real, sin mocks."""

import chess
import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert isinstance(response.json()["error"]["message"], str)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("level", [1, 10, 20])
@pytest.mark.parametrize("black_to_move", [False, True])
def test_legal_move_and_contract(client, level, black_to_move):
    board = chess.Board()
    if black_to_move:
        board.push_uci("e2e4")
    response = client.post("/engine/best-move", json={"fen": board.fen(), "level": level})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"uci", "san", "evaluation"}
    move = chess.Move.from_uci(body["uci"])
    assert move in board.legal_moves
    assert body["san"] == board.san(move)
    assert body["evaluation"]["type"] in ("cp", "mate")
    assert type(body["evaluation"]["value"]) is int


def test_legacy_java_contract(client):
    response = client.post("/best-move", json={"fen": chess.STARTING_FEN, "level": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["move"] == body["uci"]
    assert chess.Move.from_uci(body["move"]) in chess.Board().legal_moves


@pytest.mark.parametrize("fen", [
    "not a fen", "8/8/8/8/8/8/8/8 w - - 0 1",
    "8/8/8/8/8/8/8/8 w - -", "9/8/8/8/8/8/8/K6k w - - 0 1",
])
def test_invalid_fen(client, fen):
    assert_error(client.post("/engine/best-move", json={"fen": fen, "level": 10}),
                 400, "INVALID_FEN")


@pytest.mark.parametrize("level", [0, 21, 1.5, "10", True, None])
def test_invalid_level(client, level):
    assert_error(client.post("/engine/best-move", json={"fen": chess.STARTING_FEN, "level": level}),
                 400, "VALIDATION_ERROR")


@pytest.mark.parametrize("body", [{}, {"fen": chess.STARTING_FEN}, {"fen": 123, "level": 1}])
def test_missing_or_wrong_fields(client, body):
    assert_error(client.post("/engine/best-move", json=body), 400, "VALIDATION_ERROR")


def test_malformed_json(client):
    assert_error(client.post("/engine/best-move", content="{", headers={"Content-Type": "application/json"}),
                 400, "VALIDATION_ERROR")


@pytest.mark.parametrize("fen", [
    "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1",  # Jaque mate.
    "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1",  # Ahogado.
])
def test_no_legal_moves(client, fen):
    assert_error(client.post("/engine/best-move", json={"fen": fen, "level": 20}),
                 422, "NO_LEGAL_MOVES")


@pytest.mark.parametrize("black_to_move", [False, True])
def test_mate_score_from_side_to_move(client, black_to_move):
    board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 w - - 0 1")
    if black_to_move:
        board = board.mirror()
    response = client.post("/engine/best-move", json={"fen": board.fen(), "level": 20})
    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"] == {"type": "mate", "value": 1}
    board.push_uci(body["uci"])
    assert board.is_checkmate()


def test_promotion(client):
    # La única salida del jaque es gxh8 con promoción; no depende de preferencias del motor.
    board = chess.Board("7r/6P1/8/8/8/8/5k2/7K w - - 0 1")
    response = client.post("/engine/best-move", json={"fen": board.fen(), "level": 20})
    assert response.status_code == 200
    move = board.parse_uci(response.json()["uci"])
    assert move.promotion is not None
    assert response.json()["san"] == board.san(move)


def test_busy_engine_returns_recoverable_error(client):
    with app.state.engine.lock:
        assert_error(client.post("/engine/best-move", json={"fen": chess.STARTING_FEN, "level": 1}),
                     503, "ENGINE_BUSY")
    assert client.get("/health").status_code == 200


def test_restart_after_engine_exit(client):
    app.state.engine.engine.quit()
    assert_error(client.get("/health"), 503, "ENGINE_UNAVAILABLE")
    response = client.post("/engine/best-move", json={"fen": chess.STARTING_FEN, "level": 1})
    assert response.status_code == 200, response.text
    assert client.get("/health").status_code == 200
