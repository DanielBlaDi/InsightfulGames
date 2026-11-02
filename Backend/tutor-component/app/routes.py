"""Rutas internas del Tutor (prefijo ``/internal/tutor/``, contrato sección 13).

El gateway web traduce las rutas públicas ``/tutor/*`` a estas y añade la
cabecera ``X-User-Id`` después de validar el JWT. Las rutas internas no se
publican hacia el exterior (sección 2).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response

from app.errors import ApiError
from app.models import AnalysisRequest, AnalysisStatus
from app.service import TutorService

router = APIRouter(prefix="/internal/tutor", tags=["tutor"])


def _service(request: Request) -> TutorService:
    service = getattr(request.app.state, "service", None)
    if service is None:
        raise ApiError(
            503, "SERVICES_UNAVAILABLE", "El Tutor no está inicializado."
        )
    return service


def _requesting_user(request: Request) -> str:
    """Identidad puesta por el gateway web en las rutas públicas."""
    raw = request.headers.get("x-user-id")
    if raw is None or not raw.strip():
        raise ApiError(401, "UNAUTHORIZED", "Falta la cabecera X-User-Id.")
    try:
        return str(uuid.UUID(raw.strip()))
    except (ValueError, AttributeError) as exc:
        raise ApiError(
            401, "UNAUTHORIZED", "La cabecera X-User-Id no es válida."
        ) from exc


@router.post(
    "/analyses",
    response_model=AnalysisStatus,
    status_code=202,
    responses={
        200: {
            "model": AnalysisStatus,
            "description": "Ya existía un análisis con la misma clave.",
        }
    },
)
async def request_analysis(
    payload: AnalysisRequest, request: Request, response: Response
):
    """Crea el análisis (202) o devuelve el existente (200)."""
    view, created = await _service(request).request_analysis(
        payload, _requesting_user(request)
    )
    response.status_code = 202 if created else 200
    return view


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisStatus,
    responses={404: {"description": "ANALYSIS_NOT_FOUND"}},
)
async def get_analysis(analysis_id: str, request: Request):
    """Estado del análisis: pending, processing, completed o failed."""
    return await _service(request).get_analysis(
        analysis_id, _requesting_user(request)
    )


@router.get(
    "/analyses/{analysis_id}/result",
    responses={
        200: {"description": "Informe completo (solo si completed)"},
        404: {"description": "ANALYSIS_NOT_FOUND"},
        409: {"description": "ANALYSIS_NOT_READY"},
    },
)
async def get_analysis_result(analysis_id: str, request: Request):
    """Informe final con summary, moves y explanation.

    No usa ``response_model`` a propósito: el contenido de ``summary`` y
    ``moves`` lo escribe el Analysis Worker y se entrega tal cual, para no
    recortar campos que el worker agregue dentro del contrato.
    """
    return await _service(request).get_result(
        analysis_id, _requesting_user(request)
    )


@router.delete(
    "/users/{user_id}",
    status_code=204,
    responses={204: {"description": "Borrado idempotente, exista o no el usuario"}},
)
async def delete_user(user_id: str, request: Request):
    """Anonimiza requestedBy y borra los análisis privados del usuario."""
    await _service(request).delete_user(user_id)
    return Response(status_code=204)
