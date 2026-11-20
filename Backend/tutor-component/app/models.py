"""Modelos de entrada y salida del Tutor (contrato, sección 16.4).

El JSON del contrato usa camelCase. Los modelos de este módulo son DTO de
transporte; el documento interno de MongoDB también usa camelCase para que el
Analysis Worker pueda leerlo sin traducciones.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.timeutils import to_iso

AnalysisStatusValue = Literal["pending", "processing", "completed", "failed"]


class AnalysisRequest(BaseModel):
    """Cuerpo de POST /internal/tutor/analyses."""

    model_config = ConfigDict(extra="ignore")

    gameId: str = Field(min_length=1, max_length=64)
    language: str = Field(default="es", min_length=1, max_length=16)
    detailLevel: str = Field(default="standard", min_length=1, max_length=32)
    depth: int | None = Field(
        default=None,
        strict=True,
        description="Profundidad del análisis. Si se omite se usa ANALYSIS_DEPTH_DEFAULT.",
    )


class AnalysisStatus(BaseModel):
    """Estado de un análisis (respuesta de POST y de GET /analyses/{id})."""

    analysisId: str
    gameId: str
    status: AnalysisStatusValue
    engineVersion: str
    depth: int
    language: str
    detailLevel: str
    createdAt: str | None = None
    updatedAt: str | None = None
    # Mensaje seguro cuando status es failed (sección 16.4.2: el usuario lo ve en el estado).
    error: str | None = None
    # True solo si un POST con la misma clave puede reactivar el análisis.
    retryable: bool = False


def is_retryable(document: dict[str, Any], max_reactivations: int) -> bool:
    """Indica si el análisis failed puede reactivarse (sección 16.4.3).

    Solo los fallos transitorios lo son y solo mientras queden reactivaciones.
    Con ``ANALYSIS_MAX_REACTIVATIONS=0`` la reactivación queda desactivada.
    """
    if max_reactivations <= 0:
        return False
    if document.get("status") != "failed":
        return False
    if document.get("failureKind") != "transient":
        return False
    reactivations = document.get("reactivations", 0)
    if not isinstance(reactivations, int) or isinstance(reactivations, bool):
        return False
    return reactivations < max_reactivations


def status_payload(
    document: dict[str, Any], max_reactivations: int = 0
) -> dict[str, Any]:
    """Vista pública del documento de análisis."""
    return {
        "analysisId": document.get("analysisId") or document.get("_id"),
        "gameId": document.get("gameId"),
        "status": document.get("status", "pending"),
        "engineVersion": document.get("engineVersion", ""),
        "depth": int(document.get("depth") or 0),
        "language": document.get("language", "es"),
        "detailLevel": document.get("detailLevel", "standard"),
        "createdAt": to_iso(document.get("createdAt")),
        "updatedAt": to_iso(document.get("updatedAt") or document.get("createdAt")),
        "error": document.get("error"),
        "retryable": is_retryable(document, max_reactivations),
    }


def result_parts(document: dict[str, Any]) -> tuple[Any, Any] | None:
    """Extrae ``summary`` y ``moves`` del documento.

    La forma canónica que escribe el Analysis Worker es
    ``result: { summary, moves }``. Se tolera que los campos estén en la raíz
    del documento para no romper si el worker los guarda planos.
    """
    result = document.get("result")
    if isinstance(result, dict) and ("summary" in result or "moves" in result):
        return result.get("summary") or {}, result.get("moves") or []
    if "summary" in document or "moves" in document:
        return document.get("summary") or {}, document.get("moves") or []
    return None
