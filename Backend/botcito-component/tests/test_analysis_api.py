
"""Pruebas HTTP independientes de Botcito-analisis."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def run_analysis_test(code: str):
    """Ejecuta una prueba con ENGINE_ROLE=analysis."""

    env = os.environ.copy()
    env.update({
        "ENGINE_ROLE": "analysis",
        "ENGINE_TIMEOUT_MS": "10000",
        "ANALYSIS_DEPTH_MAX": "18",
    })

    imports = """
import chess
from fastapi.testclient import TestClient
from main import app
"""

    script = textwrap.dedent(imports) + textwrap.dedent(code)

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, (
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )


def test_active_position():
    """Verifica la evaluacion de una posicion activa."""

    run_analysis_test("""
with TestClient(app) as client:
    response = client.post(
        "/internal/engine-analysis/evaluate",
        json={
            "fen": chess.STARTING_FEN,
            "depth": 8
        }
    )

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
""")


def test_terminal_positions():
    """Verifica jaque mate y ahogado."""

    run_analysis_test("""
positions = [
    ("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", 100000),
    ("7K/6q1/6k1/8/8/8/8/8 w - - 0 1", -100000),
    ("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", 0),
]

with TestClient(app) as client:
    for fen, expected in positions:
        response = client.post(
            "/internal/engine-analysis/evaluate",
            json={
                "fen": fen,
                "depth": 8
            }
        )

        assert response.status_code == 200, response.text

        data = response.json()

        assert data["evaluation"]["type"] == "cp"
        assert data["evaluation"]["value"] == expected
        assert data["evaluation"]["perspective"] == "white"
        assert data["bestMove"] is None
""")


def test_invalid_depth():
    """Verifica las restricciones de profundidad."""

    run_analysis_test("""
with TestClient(app) as client:
    for depth in [0, 19, "8"]:
        response = client.post(
            "/internal/engine-analysis/evaluate",
            json={
                "fen": chess.STARTING_FEN,
                "depth": depth
            }
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    response = client.post(
        "/internal/engine-analysis/evaluate",
        json={"fen": chess.STARTING_FEN}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
""")


def test_invalid_fen():
    """Verifica el rechazo de posiciones invalidas."""

    run_analysis_test("""
with TestClient(app) as client:
    response = client.post(
        "/internal/engine-analysis/evaluate",
        json={
            "fen": "invalid",
            "depth": 8
        }
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FEN"
""")


def test_role_isolation():
    """Verifica que analysis no exponga las rutas de juego."""

    run_analysis_test("""
with TestClient(app) as client:
    response = client.post(
        "/internal/engine/best-move",
        json={
            "fen": chess.STARTING_FEN,
            "botLevel": 10
        }
    )

    assert response.status_code == 404
""")


def test_engine_busy():
    """Verifica la saturacion del pool de motores."""

    run_analysis_test("""
with TestClient(app) as client:
    pool = app.state.engine
    acquired = []

    try:
        for slot in pool.slots:
            assert slot.lock.acquire(blocking=False)
            acquired.append(slot)

        response = client.post(
            "/internal/engine-analysis/evaluate",
            json={
                "fen": chess.STARTING_FEN,
                "depth": 8
            }
        )

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "ENGINE_BUSY"

    finally:
        for slot in acquired:
            slot.lock.release()
""")


def test_engine_timeout_and_recovery():
    """Verifica HTTP 504 y recuperacion tras un timeout."""

    run_analysis_test("""
import chess.engine
from unittest.mock import patch

payload = {
    "fen": chess.STARTING_FEN,
    "depth": 8
}

with TestClient(app) as client:

    # Simular que Stockfish supera el tiempo permitido.
    with patch.object(
        chess.engine.SimpleEngine,
        "analyse",
        side_effect=TimeoutError("Timeout simulado")
    ):
        response = client.post(
            "/internal/engine-analysis/evaluate",
            json=payload
        )

    assert response.status_code == 504, response.text
    assert response.json()["error"]["code"] == "ENGINE_TIMEOUT"

    # Comprobar que el servicio puede atender otra solicitud.
    response = client.post(
        "/internal/engine-analysis/evaluate",
        json=payload
    )

    assert response.status_code == 200, response.text
    assert response.json()["bestMove"] is not None
    assert response.json()["evaluation"]["perspective"] == "white"
""")


def test_engine_failure_and_restart():
    """Verifica que un motor fallido se reinicia individualmente."""

    run_analysis_test("""
import chess.engine
from unittest.mock import patch

payload = {
    "fen": chess.STARTING_FEN,
    "depth": 8
}

with TestClient(app) as client:
    pool = app.state.engine

    assert len(pool.slots) == 2

    first_slot = pool.slots[0]
    second_slot = pool.slots[1]

    original_engine = first_slot.engine

    # Ocupamos el segundo motor para obligar a utilizar el primero.
    assert second_slot.lock.acquire(blocking=False)

    try:
        # Simular un fallo del primer motor.
        with patch.object(
            chess.engine.SimpleEngine,
            "analyse",
            side_effect=RuntimeError("Fallo UCI simulado")
        ):
            response = client.post(
                "/internal/engine-analysis/evaluate",
                json=payload
            )

        assert response.status_code == 503, response.text
        assert (
            response.json()["error"]["code"]
            == "SERVICES_UNAVAILABLE"
        )

        # El motor afectado debe quedar descartado.
        assert first_slot.engine is None

        # La siguiente solicitud debe recuperar ese mismo slot.
        response = client.post(
            "/internal/engine-analysis/evaluate",
            json=payload
        )

        assert response.status_code == 200, response.text

        data = response.json()

        assert data["bestMove"] is not None
        assert data["evaluation"]["perspective"] == "white"

        # Comprobar que se creo otro proceso de motor.
        assert first_slot.engine is not None
        assert first_slot.engine is not original_engine

        print("Motor recuperado correctamente")

    finally:
        second_slot.lock.release()
""")
