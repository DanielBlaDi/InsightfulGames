
"""Pruebas HTTP de Botcito-analisis en un proceso independiente."""

import os
import subprocess
import sys
from pathlib import Path


def test_analysis_api_contract():
    env = os.environ.copy()
    env.update({
        "ENGINE_ROLE": "analysis",
        "ENGINE_TIMEOUT_MS": "10000",
        "ANALYSIS_DEPTH_MAX": "18",
    })

    script = """
import chess
from fastapi.testclient import TestClient
from main import app

route = "/internal/engine-analysis/evaluate"

with TestClient(app) as client:

    # 1. Posicion activa
    response = client.post(route, json={
        "fen": chess.STARTING_FEN,
        "depth": 8
    })

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["fen"] == chess.STARTING_FEN
    assert data["depth"] == 8
    assert data["evaluation"]["perspective"] == "white"
    assert data["evaluation"]["type"] in ("cp", "mate")
    assert data["bestMove"] is not None

    board = chess.Board(chess.STARTING_FEN)
    move = chess.Move.from_uci(data["bestMove"]["uci"])

    assert move in board.legal_moves
    assert data["bestMove"]["san"] == board.san(move)

    # 2. Posiciones terminales
    positions = [
        ("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", 100000),
        ("7K/6q1/6k1/8/8/8/8/8 w - - 0 1", -100000),
        ("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", 0),
    ]

    for fen, expected in positions:
        response = client.post(route, json={
            "fen": fen,
            "depth": 8
        })

        assert response.status_code == 200, response.text
        data = response.json()

        assert data["evaluation"]["type"] == "cp"
        assert data["evaluation"]["value"] == expected
        assert data["evaluation"]["perspective"] == "white"
        assert data["bestMove"] is None

    # 3. Profundidad invalida
    for depth in [0, 19, "8"]:
        response = client.post(route, json={
            "fen": chess.STARTING_FEN,
            "depth": depth
        })

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    # 4. FEN invalido
    response = client.post(route, json={
        "fen": "invalid",
        "depth": 8
    })

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FEN"

    # 5. El rol analysis no expone rutas de juego
    response = client.post(
        "/internal/engine/best-move",
        json={
            "fen": chess.STARTING_FEN,
            "botLevel": 10
        }
    )

    assert response.status_code == 404

print("Contrato de Botcito-analisis correcto")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, (
        f"STDOUT:\\n{result.stdout}\\nSTDERR:\\n{result.stderr}"
    )
