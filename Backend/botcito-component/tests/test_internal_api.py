import chess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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


def test_internal_uses_second_engine_if_first_busy():
    fen = chess.STARTING_FEN

    with TestClient(app) as client:
        pool = app.state.engine

        with pool.slots[0].lock:
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
    assert chess.Move.from_uci(data["uci"]) in board.legal_moves


def test_internal_returns_busy_if_all_engines_busy():
    fen = chess.STARTING_FEN

    with TestClient(app) as client:
        pool = app.state.engine

        with pool.slots[0].lock, pool.slots[1].lock:
            response = client.post(
                "/internal/engine/best-move",
                json={
                    "fen": fen,
                    "botLevel": 10
                }
            )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ENGINE_BUSY"


def test_two_real_requests_run_in_parallel():
    """Verifica dos solicitudes simultaneas con Stockfish real."""

    fen = chess.STARTING_FEN

    with TestClient(app) as client:
        pool = app.state.engine

        assert len(pool.slots) == 2

        # Sincroniza el inicio de ambas solicitudes.
        barrier = threading.Barrier(3)

        def send_request():
            barrier.wait(timeout=10)

            return client.post(
                "/internal/engine/best-move",
                json={
                    "fen": fen,
                    "botLevel": 10
                }
            )

        with ThreadPoolExecutor(max_workers=2) as executor:

            futures = [
                executor.submit(send_request)
                for _ in range(2)
            ]

            # Permitir que ambas solicitudes comiencen.
            barrier.wait(timeout=10)

            # Detectar si ambos motores trabajan a la vez.
            both_busy = False
            deadline = time.monotonic() + 10

            while time.monotonic() < deadline:

                if all(slot.lock.locked() for slot in pool.slots):
                    both_busy = True
                    break

                if all(f.done() for f in futures):
                    break

                time.sleep(0.005)

            responses = [
                future.result(timeout=15)
                for future in futures
            ]

        # Ambos motores debieron estar ocupados al mismo tiempo.
        assert both_busy, (
            "No se detectaron dos motores ocupados simultaneamente."
        )

        # Ambas peticiones deben terminar correctamente.
        for response in responses:
            assert response.status_code == 200, response.text

            data = response.json()
            board = chess.Board(fen)
            move = chess.Move.from_uci(data["uci"])

            assert move in board.legal_moves
            assert data["evaluation"]["perspective"] == "side_to_move"


def test_internal_engine_timeout(monkeypatch):
    """Verifica la respuesta cuando Stockfish supera el timeout."""

    with TestClient(app) as client:
        pool = app.state.engine

        first_slot = pool.slots[0]
        second_slot = pool.slots[1]

        assert first_slot.engine is not None
        assert second_slot.engine is not None

        second_engine = second_slot.engine

        # Simular un timeout al calcular la jugada.
        def simulate_timeout(*args, **kwargs):
            raise TimeoutError("Stockfish timeout simulado")

        monkeypatch.setattr(
            first_slot.engine,
            "play",
            simulate_timeout
        )

        response = client.post(
            "/internal/engine/best-move",
            json={
                "fen": chess.STARTING_FEN,
                "botLevel": 10
            }
        )

        # El contrato exige HTTP 504.
        assert response.status_code == 504

        data = response.json()
        assert data["error"]["code"] == "ENGINE_TIMEOUT"

        # El motor afectado debe descartarse.
        assert first_slot.engine is None

        # El segundo motor debe seguir funcionando.
        assert second_slot.engine is second_engine
        assert pool.healthy()

        # El servicio debe permanecer disponible.
        assert client.get("/health").status_code == 200


def test_internal_engine_unavailable(monkeypatch):
    """Verifica la recuperacion despues de un fallo del motor."""

    with TestClient(app) as client:
        pool = app.state.engine

        first_slot = pool.slots[0]
        second_slot = pool.slots[1]

        assert first_slot.engine is not None
        assert second_slot.engine is not None

        first_engine = first_slot.engine
        second_engine = second_slot.engine

        # Simular un fallo inesperado al calcular una jugada.
        def simulate_failure(*args, **kwargs):
            raise RuntimeError("Fallo simulado de Stockfish")

        monkeypatch.setattr(
            first_engine,
            "play",
            simulate_failure
        )

        response = client.post(
            "/internal/engine/best-move",
            json={
                "fen": chess.STARTING_FEN,
                "botLevel": 10
            }
        )

        # Verificar el error contractual.
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SERVICES_UNAVAILABLE"

        # Solo se descarta el motor afectado.
        assert first_slot.engine is None

        # El segundo motor permanece operativo.
        assert second_slot.engine is second_engine
        assert pool.healthy()

        # La siguiente peticion debe recuperar el primer motor.
        recovery = client.post(
            "/internal/engine/best-move",
            json={
                "fen": chess.STARTING_FEN,
                "botLevel": 10
            }
        )

        assert recovery.status_code == 200, recovery.text

        # Se creo un proceso nuevo para el primer espacio.
        assert first_slot.engine is not None
        assert first_slot.engine is not first_engine
        assert not first_slot.engine.returncode.done()

        # El segundo proceso no fue reemplazado.
        assert second_slot.engine is second_engine
