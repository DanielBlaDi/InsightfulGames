"""Verifica que Stockfish pueda iniciar lentamente."""

import sys

from main import StockfishEngine


def test_slow_stockfish_startup(monkeypatch):
    # Utilizamos un motor para aislar esta prueba.
    monkeypatch.setenv("ENGINE_POOL_SIZE", "1")

    engine = StockfishEngine()

    # Simula un retraso de 3 segundos antes de iniciar Stockfish.
    # subprocess funciona tanto en Windows como en Linux.
    engine.path = [
        sys.executable,
        "-u",
        "-c",
        (
            "import subprocess,sys,time; "
            "time.sleep(3); "
            "sys.exit(subprocess.call([sys.argv[1]]))"
        ),
        engine.path,
    ]

    try:
        engine.start(startup_timeout=30.0)

        assert engine.healthy()
        assert engine.slots[0].engine is not None

        # El timeout normal sigue siendo de 2 segundos.
        assert engine.slots[0].engine.timeout == 2.0

        # Comprobar comunicacion con el motor.
        engine.slots[0].engine.ping()
        engine.slots[0].engine.quit()

    finally:
        engine.close()
