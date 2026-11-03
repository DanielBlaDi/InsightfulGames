import chess
from fastapi.testclient import TestClient

from main import app


def test_internal_best_move_contract():
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    with TestClient(app) as client:
        response = client.post(
            "/internal/engine/best-move",
            json={
                "fen": fen,
                "botLevel": 10
            }
        )

    assert response.status_code == 200

    data = response.json()

    board = chess.Board(fen)
    move = chess.Move.from_uci(data["uci"])

    assert move in board.legal_moves
    assert data["san"] == board.san(move)
    assert data["evaluation"]["type"] in ("cp", "mate")
    assert isinstance(data["evaluation"]["value"], int)
    assert data["evaluation"]["perspective"] == "side_to_move"


import pytest

@pytest.mark.parametrize("invalid_level", [0, 21, "10"])
def test_internal_best_move_invalid_level(invalid_level):
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    with TestClient(app) as client:
        response = client.post(
            "/internal/engine/best-move",
            json={
                "fen": fen,
                "botLevel": invalid_level
            }
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

