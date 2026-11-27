"""Pone en sys.path el paquete compartido `orchestration` (Backend/gateway-shared), como en la imagen Docker."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway-shared"))