"""Validaciones de entrada que responden VALIDATION_ERROR (400)."""

from __future__ import annotations

import html
import re
import uuid

from app.errors import ApiError


# Patrones peligrosos para XSS
XSS_PATTERNS = [
    r'<script\b[^>]*>.*?</script>',
    r'javascript:',
    r'on\w+\s*=',
    r'<iframe\b',
    r'<object\b',
    r'<embed\b',
    r'<form\b',
    r'<input\b',
    r'<meta\b',
    r'<link\b',
    r'expression\s*\(',
    r'vbscript:',
    r'data:text/html',
]


def contains_xss(value: str) -> bool:
    """Detecta patrones comunes de XSS en el input."""
    if not isinstance(value, str):
        return False
    lower = value.lower()
    for pattern in XSS_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE | re.DOTALL):
            return True
    return False


def sanitize_text_input(value: str, max_length: int) -> str:
    """
    Sanitiza texto de entrada del usuario.

    - Escapa HTML
    - Detecta y rechaza patrones XSS
    - Limita longitud
    """
    if not isinstance(value, str):
        raise ValueError("El valor debe ser un string")

    # Detectar XSS antes de sanitizar
    if contains_xss(value):
        raise ValueError("Entrada contiene patrones no permitidos")

    # Escapar HTML
    escaped = html.escape(value, quote=True)

    # Limitar longitud
    if len(escaped) > max_length:
        raise ValueError(f"El texto excede el máximo de {max_length} caracteres")

    return escaped


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
    # Verificar XSS
    if contains_xss(normalized):
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            f"El campo {field_name} contiene caracteres no permitidos.",
        )
    return normalized


def normalize_sanitized_text(value: str | None, field_name: str, max_length: int) -> str:
    """
    Normaliza y sanitiza texto, escapando HTML y validando XSS.
    Para campos que se mostrarán al usuario (language, detailLevel).
    """
    if not isinstance(value, str) or not value.strip():
        raise ApiError(
            400, "VALIDATION_ERROR", f"El campo {field_name} es obligatorio."
        )
    try:
        return sanitize_text_input(value.strip(), max_length)
    except ValueError as exc:
        raise ApiError(400, "VALIDATION_ERROR", str(exc)) from exc


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
