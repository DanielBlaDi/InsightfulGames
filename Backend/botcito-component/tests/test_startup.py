"""Un arranque lento no debe usar el límite corto de las consultas."""

import sys

from main import StockfishEngine


def test_slow_stockfish_startup():
    engine = StockfishEngine()
    # Retrasa el lanzamiento del binario real, como un arranque con carga de CPU.
    engine.path = [
        sys.executable, "-c",
        "import os,sys,time; time.sleep(3); os.execv(sys.argv[1], [sys.argv[1]])",
        engine.path,
    ]
    try:
        engine.start(startup_timeout=30.0)
        assert engine.healthy()
        assert engine.engine.timeout == 2.0
        engine.engine.ping()
    finally:
        engine.close()
