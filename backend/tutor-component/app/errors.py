"""Error de API con el formato común del contrato (sección 1).

Formato de respuesta:

    { "error": { "code": "GAME_NOT_FOUND", "message": "..." } }

Los códigos usados por el Tutor están en la sección 20 del contrato.
"""

from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message

    def payload(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}
