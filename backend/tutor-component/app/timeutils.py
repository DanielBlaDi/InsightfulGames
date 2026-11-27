"""Fechas en UTC con el formato ISO 8601 del contrato (sección 1)."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime | str | None) -> str | None:
    """Convierte una fecha a ``2026-10-29T15:30:00Z``.

    Mongo devuelve ``datetime`` sin zona si el cliente no es ``tz_aware``; en ese
    caso se asume UTC, que es como el contrato guarda todas las fechas.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")
