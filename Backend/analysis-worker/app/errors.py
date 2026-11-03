"""Errores internos del Analysis Worker.

La clasificación sigue la tabla de fallos del contrato (sección 16.4.3):

* ``transient``: motor ocupado, timeout, red o 5xx. Se reintenta por evaluación
  y, agotados los intentos, el análisis pasa a ``failed`` con
  ``failureKind: transient``.
* ``permanent``: datos de entrada inválidos o inconsistentes. El análisis pasa
  a ``failed`` con ``failureKind: permanent`` y no se reintenta.
"""

from __future__ import annotations

from typing import Literal

FailureKind = Literal["transient", "permanent"]


class AnalysisFailure(Exception):
    """Fallo clasificado durante el procesamiento de un análisis."""

    def __init__(
        self,
        message: str,
        *,
        failure_kind: FailureKind,
        code: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.failure_kind = failure_kind
        self.code = code

    @property
    def transient(self) -> bool:
        return self.failure_kind == "transient"


class MessageValidationError(Exception):
    """Mensaje de RabbitMQ que no cumple el contrato del evento."""


class LeaseLostError(Exception):
    """El worker perdió el lease y debe descartar el trabajo en curso."""
