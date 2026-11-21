"""Errores del gateway y tabla de traducción de errores de servicios (contrato 4.1 y 7.3)."""

from typing import Any, Mapping

import httpx


class GatewayError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class UpstreamUnreachable(GatewayError):
    def __init__(self) -> None:
        super().__init__(503, "SERVICES_UNAVAILABLE", "Servicio destino no disponible")


class UpstreamTimeout(GatewayError):
    def __init__(self) -> None:
        super().__init__(503, "SERVICES_UNAVAILABLE", "El servicio destino no respondió a tiempo")


class FlowError(GatewayError):
    """Error de un flow de orquestación. Se traduce igual que cualquier GatewayError."""


# Errores 5xx del catálogo que pasan con su código y estado reales (contrato, 4.5)
CATALOG_5XX: dict[str, int] = {
    "SERVICES_UNAVAILABLE": 503,
    "ENGINE_BUSY": 503,
    "ENGINE_TIMEOUT": 504,
}


def upstream_flow_error(response: httpx.Response, name: str) -> FlowError:
    """Convierte una respuesta de error de Game Logic o Botcito en un FlowError.

    Los 4xx conservan estado y código (ya vienen con la forma del contrato). Los 5xx conservan
    ENGINE_BUSY (503), ENGINE_TIMEOUT (504) y SERVICES_UNAVAILABLE (503); cualquier otro 5xx pasa a
    503 SERVICES_UNAVAILABLE.
    """
    payload = payload_of(response)
    code = message = None
    if is_contract_error(payload):
        code, message = payload["error"]["code"], payload["error"]["message"]

    status = response.status_code
    if status >= 500 or status < 400:
        if code in CATALOG_5XX:
            return FlowError(CATALOG_5XX[code], code, message or f"{name} no está disponible")
        return FlowError(503, "SERVICES_UNAVAILABLE", f"{name} respondió con error {status}")
    return FlowError(status, code or "UPSTREAM_ERROR", message or f"{name} respondió {status}")


def deletion_unavailable(name: str) -> FlowError:
    """503 del borrado de cuenta: nombra el servicio que no respondió (el usuario puede reintentar)."""
    return FlowError(
        503,
        "SERVICES_UNAVAILABLE",
        f"No se pudo borrar la cuenta: {name} no respondió. Intenta de nuevo",
    )


# Código 404 según el servicio de origen (traducción de errores, 7.3)
NOT_FOUND_CODE: dict[str, str] = {
    "single-player": "GAME_NOT_FOUND",
    "logic": "GAME_NOT_FOUND",
    "multiplayer": "MATCH_NOT_FOUND",
    "tutor": "ANALYSIS_NOT_FOUND",
    "profile": "PROFILE_NOT_FOUND",
}


def payload_of(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def is_contract_error(payload: Any) -> bool:
    """¿Viene con el formato común {error: {code, message}}?"""
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("error"), dict)
        and bool(payload["error"].get("code"))
        and bool(payload["error"].get("message"))
    )


def translate_error(
    status: int,
    *,
    service: str,
    conflict_code: str | None = None,
    unauthorized_code: str = "UNAUTHORIZED",
    not_found_codes: Mapping[str, str] = NOT_FOUND_CODE,
) -> tuple[int, str, str]:
    """Estado, código y mensaje públicos para un error sin formato común."""
    table: dict[int, tuple[int, str, str]] = {
        400: (400, "VALIDATION_ERROR", "Campos faltantes o con formato inválido"),
        401: (401, unauthorized_code, "No autorizado"),
        404: (404, not_found_codes.get(service, "NOT_FOUND"), "Recurso no encontrado"),
        503: (503, "SERVICES_UNAVAILABLE", "Un servicio dependiente no responde"),
        504: (503, "SERVICES_UNAVAILABLE", "Un servicio dependiente no respondió a tiempo"),
    }
    if conflict_code:
        table[409] = (409, conflict_code, "Conflicto con el estado actual")
    return table.get(status, (502, "UPSTREAM_ERROR", "El servicio devolvió un error"))


def flow_error_from(
    response: httpx.Response,
    *,
    service: str,
    conflict_code: str | None = None,
    unauthorized_code: str = "UNAUTHORIZED",
) -> FlowError:
    """Convierte una respuesta de error de un servicio en un FlowError: los errores
    con formato común pasan tal cual; el resto se traduce con la tabla compartida."""
    payload = payload_of(response)
    if is_contract_error(payload):
        error = payload["error"]
        return FlowError(response.status_code, error["code"], error["message"])
    status, code, message = translate_error(
        response.status_code,
        service=service,
        conflict_code=conflict_code,
        unauthorized_code=unauthorized_code,
    )
    return FlowError(status, code, message)
