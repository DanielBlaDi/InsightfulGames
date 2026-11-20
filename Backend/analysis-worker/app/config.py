"""Configuración del Analysis Worker (contrato, sección 17.5)."""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass, field

# Topología fija del contrato (secciones 17 y 19).
TUTOR_EVENTS_EXCHANGE = "tutor.events"
ANALYSIS_REQUESTED_ROUTING_KEY = "tutor.analysis.requested"
MAIN_QUEUE = "analysis-worker.requested"
WAIT_QUEUE = "analysis-worker.requested.wait"
DLQ = "analysis-worker.requested.dlq"
RETRY_EXCHANGE = "retry.events"
RETRY_TTL_MS = 5000

# Seis intentos totales del broker: uno inicial y cinco reintentos.
MAX_BROKER_RETRIES = 5

# Pausas entre los intentos por evaluación (sección 16.4.3).
RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0, 8.0)


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


def _default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class Settings:
    """Variables de entorno del worker.

    ``ANALYSIS_MAX_RETRIES`` tiene el doble uso que reconoce el contrato:
    intentos por evaluación y límite de reclamos de un análisis.
    """

    port: int = 8089
    gateway_internal_url: str = "http://api-gateway-component:8080"
    mongo_analysis_url: str = "mongodb://localhost:27017"
    mongo_analysis_database: str = "insightful_analysis"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    analysis_depth_max: int = 18
    analysis_max_retries: int = 5
    analysis_inaccuracy_cp: int = 50
    analysis_mistake_cp: int = 100
    analysis_blunder_cp: int = 300
    poll_interval_seconds: float = 5.0
    analysis_stale_minutes: float = 5.0
    http_timeout: float = 15.0
    log_level: str = "INFO"
    worker_id: str = field(default_factory=_default_worker_id)

    @property
    def stale_seconds(self) -> float:
        return self.analysis_stale_minutes * 60.0

    @property
    def renewal_interval_seconds(self) -> float:
        # Renovación cada ANALYSIS_STALE_MINUTES / 3 (sección 17.4.1).
        return max(self.stale_seconds / 3.0, 0.01)

    @classmethod
    def from_env(cls) -> "Settings":
        port = _int_env("PORT", 8089)
        if not 1 <= port <= 65535:
            raise ValueError("PORT debe ser un puerto válido")

        depth_max = _int_env("ANALYSIS_DEPTH_MAX", 18)
        if depth_max < 1:
            raise ValueError("ANALYSIS_DEPTH_MAX debe ser mayor o igual a 1")

        max_retries = _int_env("ANALYSIS_MAX_RETRIES", 5)
        if max_retries < 1:
            raise ValueError("ANALYSIS_MAX_RETRIES debe ser mayor o igual a 1")

        inaccuracy = _int_env("ANALYSIS_INACCURACY_CP", 50)
        mistake = _int_env("ANALYSIS_MISTAKE_CP", 100)
        blunder = _int_env("ANALYSIS_BLUNDER_CP", 300)
        if not 0 <= inaccuracy < mistake < blunder:
            raise ValueError(
                "Los umbrales deben cumplir 0 <= ANALYSIS_INACCURACY_CP < "
                "ANALYSIS_MISTAKE_CP < ANALYSIS_BLUNDER_CP"
            )

        poll_interval = _float_env("POLL_INTERVAL_SECONDS", 5.0)
        if poll_interval <= 0:
            raise ValueError("POLL_INTERVAL_SECONDS debe ser mayor que 0")

        stale_minutes = _float_env("ANALYSIS_STALE_MINUTES", 5.0)
        if stale_minutes <= 0:
            raise ValueError("ANALYSIS_STALE_MINUTES debe ser mayor que 0")

        http_timeout = _float_env("HTTP_TIMEOUT", 15.0)
        if http_timeout <= 0:
            raise ValueError("HTTP_TIMEOUT debe ser mayor que 0")

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
            analysis_depth_max=depth_max,
            analysis_max_retries=max_retries,
            analysis_inaccuracy_cp=inaccuracy,
            analysis_mistake_cp=mistake,
            analysis_blunder_cp=blunder,
            poll_interval_seconds=poll_interval,
            analysis_stale_minutes=stale_minutes,
            http_timeout=http_timeout,
            log_level=_text_env("LOG_LEVEL", "INFO").upper(),
            worker_id=_text_env("WORKER_ID", _default_worker_id()),
        )
