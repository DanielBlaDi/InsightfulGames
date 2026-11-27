"""Validaciones de entrada que responden VALIDATION_ERROR (400)."""

from __future__ import annotations

import uuid

from app.errors import ApiError


def normalize_uuid(value: str | None, field_name: str) -> str:
    """Normaliza un UUID v4 recibido como texto.

    Se aceptan mayúsculas y llaves porque ``uuid.UUID`` lo permite; lo que se
    guarda y se consulta siempre es la forma canónica en minúsculas.
    """
    if not isinstance(value, str) or not value.strip():
        raise ApiError(
            400, "VALIDATION_ERROR", f"El campo {field_name} es obligatorio."
        )
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            f"El campo {field_name} debe ser un UUID v4 válido.",
        ) from exc


def normalize_text(value: str | None, field_name: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(
            400, "VALIDATION_ERROR", f"El campo {field_name} es obligatorio."
        )
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            f"El campo {field_name} admite como máximo {max_length} caracteres.",
        )
    return normalized


def normalize_depth(value: int | None, default: int, maximum: int) -> int:
    depth = default if value is None else value
    if not isinstance(depth, int) or isinstance(depth, bool):
        raise ApiError(400, "VALIDATION_ERROR", "El campo depth debe ser un entero.")
    if depth < 1 or depth > maximum:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            f"El campo depth debe estar entre 1 y {maximum}.",
        )
    return depth
