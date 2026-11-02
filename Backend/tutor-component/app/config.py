"""Configuración del Tutor leída del entorno (contrato v9, secciones 13 y 21)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Valor anónimo definido por el contrato para reemplazar un userId borrado (sección 7).
ANONYMOUS_USER_ID = "00000000-0000-0000-0000-000000000000"

# Nombres de mensajería fijados por el contrato (sección 17).
TUTOR_EVENTS_EXCHANGE = "tutor.events"
ANALYSIS_REQUESTED_ROUTING_KEY = "tutor.analysis.requested"


def _text_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un entero, se recibió {raw!r}") from exc


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un número, se recibió {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Variables de entorno del Tutor.

    La profundidad por defecto y el tope se leen solo aquí: el Analysis Worker
    ejecuta la profundidad que llega en el evento.
    """

    port: int = 8085
    gateway_internal_url: str = "http://api-gateway-component:8080"
    mongo_analysis_url: str = "mongodb://localhost:27017"
    mongo_analysis_database: str = "insightful_analysis"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    engine_version: str = "stockfish-17"
    analysis_depth_default: int = 15
    analysis_depth_max: int = 18
    llm_provider: str = "mock"
    http_timeout: float = 10.0
    log_level: str = "INFO"
    exchange: str = TUTOR_EVENTS_EXCHANGE
    routing_key: str = ANALYSIS_REQUESTED_ROUTING_KEY
    # Tiempo máximo para conectar y publicar en RabbitMQ. No es una variable
    # del contrato: la publicación nunca debe retrasar la respuesta al usuario.
    rabbitmq_timeout: float = field(default=5.0)

    @classmethod
    def from_env(cls) -> "Settings":
        depth_max = _int_env("ANALYSIS_DEPTH_MAX", 18)
        depth_default = _int_env("ANALYSIS_DEPTH_DEFAULT", 15)
        if depth_max < 1:
            raise ValueError("ANALYSIS_DEPTH_MAX debe ser mayor o igual a 1")
        if not 1 <= depth_default <= depth_max:
            raise ValueError(
                "ANALYSIS_DEPTH_DEFAULT debe estar entre 1 y ANALYSIS_DEPTH_MAX"
            )

        port = _int_env("PORT", 8085)
        if not 1 <= port <= 65535:
            raise ValueError("PORT debe ser un puerto válido")

        return cls(
            port=port,
            gateway_internal_url=_text_env(
                "GATEWAY_INTERNAL_URL", "http://api-gateway-component:8080"
            ).rstrip("/"),
            mongo_analysis_url=_text_env(
                "MONGO_ANALYSIS_URL", "mongodb://localhost:27017"
            ),
            mongo_analysis_database=_text_env(
                "MONGO_ANALYSIS_DATABASE", "insightful_analysis"
            ),
            rabbitmq_url=_text_env(
                "RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/"
            ),
            engine_version=_text_env("ENGINE_VERSION", "stockfish-17"),
            analysis_depth_default=depth_default,
            analysis_depth_max=depth_max,
            llm_provider=_text_env("LLM_PROVIDER", "mock"),
            http_timeout=_float_env("HTTP_TIMEOUT", 10.0),
            log_level=_text_env("LOG_LEVEL", "INFO").upper(),
        )
