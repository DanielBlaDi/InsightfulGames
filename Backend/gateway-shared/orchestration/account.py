"""Saga de borrado de cuenta (contrato, sección 7).

El gateway orquesta; los servicios no se llaman entre sí. Orden obligatorio:

    1. Auth     GET    /internal/auth/users/{id}      ¿existe? 404 -> no hay nada que borrar (204)
    2. Logic    DELETE /internal/logic/users/{id}     anonimiza o termina sus partidas
    3. Tutor    game-ids -> Game Logic (visibilidad de cada partida) -> POST erase   (analyses.erase_user)
    4. Profile  DELETE /internal/profile/users/{id}
    5. Auth     DELETE /internal/auth/account         borra solo la fila (X-User-Id)

Cada borrado debe dar 204. Si uno falla se corta la cadena con 503 SERVICES_UNAVAILABLE nombrando
el servicio. No hay compensación: los borrados son idempotentes, la fila de Auth va al final y el
usuario reintenta.
"""

import asyncio
import logging
from typing import Mapping

import httpx

from . import analyses, upstream
from .errors import GatewayError, deletion_unavailable as _unavailable

logger = logging.getLogger("gateway.web")


async def _step(
    client: httpx.AsyncClient,
    upstreams: Mapping[str, str],
    name: str,
    method: str,
    service: str,
    path: str,
    *,
    timeout: float,
    user_id: str | None = None,
) -> httpx.Response:
    """Llama a un servicio; un fallo de red o de tiempo cuenta como 'no respondió'."""
    try:
        return await upstream.call(
            client, upstreams[service], service, method, path,
            user_id=user_id, timeout=timeout,
        )
    except GatewayError:
        raise _unavailable(name)


async def delete_account(
    client: httpx.AsyncClient,
    upstreams: Mapping[str, str],
    user_id: str,
    *,
    timeout: float,
) -> None:
    """Ejecuta la saga. Vuelve sin error si la cuenta se borró o ya no existía; lanza FlowError
    (503 SERVICES_UNAVAILABLE) si algún paso falla. `timeout` es el de cada llamada; la saga
    entera tiene un tope de 4 veces ese valor."""

    async def run() -> None:
        exists = await _step(client, upstreams, "Auth", "GET", "auth", f"/users/{user_id}", timeout=timeout)
        if exists.status_code == 404:
            logger.info("Borrado de cuenta: el usuario ya no existe")
            return
        if exists.status_code != 200:
            logger.warning("Borrado de cuenta: Auth respondió %s al comprobar el usuario", exists.status_code)
            raise _unavailable("Auth")

        async def delete_user_in(name: str, service: str) -> None:
            response = await _step(
                client, upstreams, name, "DELETE", service, f"/users/{user_id}", timeout=timeout,
            )
            if response.status_code != 204:
                logger.warning("Borrado de cuenta: %s respondió %s; se corta la cadena", name, response.status_code)
                raise _unavailable(name)

        await delete_user_in("Game Logic", "logic")
        await analyses.erase_user(client, upstreams, user_id, timeout=timeout)  # paso del Tutor
        await delete_user_in("Profile/Stats", "profile")

        final = await _step(
            client, upstreams, "Auth", "DELETE", "auth", "/account", timeout=timeout, user_id=user_id,
        )
        if final.status_code != 204:
            logger.warning("Borrado de cuenta: Auth respondió %s al borrar la fila", final.status_code)
            raise _unavailable("Auth")

    try:
        await asyncio.wait_for(run(), timeout=4 * timeout)
    except asyncio.TimeoutError:
        logger.error("Borrado de cuenta: la saga superó el tiempo máximo")
        raise _unavailable("un servicio")
