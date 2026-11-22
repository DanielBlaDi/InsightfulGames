"""Llamada HTTP a un servicio, independiente del Request de FastAPI."""

import logging
from typing import Any

import httpx

from .errors import UpstreamTimeout, UpstreamUnreachable

logger = logging.getLogger("gateway.orchestration")


async def call(
    client: httpx.AsyncClient,
    base_url: str,
    service: str,
    method: str,
    path: str,
    *,
    user_id: str | None = None,
    params: Any = None,
    content: bytes | None = None,
    json: Any = None,
    headers: dict[str, str] | None = None,
    timeout: float,
) -> httpx.Response:
    """Llama a {base_url}/internal/{service}{path}.

    X-User-Id solo se envía si se pasa user_id. Los timeouts y fallos de conexión
    se convierten en UpstreamTimeout / UpstreamUnreachable (503 SERVICES_UNAVAILABLE).
    Las respuestas de error del servicio se devuelven sin traducir.
    """
    url = f"{base_url}/internal/{service}{path}"
    out_headers = {"Accept": "application/json", **(headers or {})}
    if user_id:
        out_headers["X-User-Id"] = user_id

    kwargs: dict[str, Any] = {"headers": out_headers, "params": params, "timeout": timeout}
    if json is not None:
        kwargs["json"] = json
    elif content is not None:
        kwargs["content"] = content

    try:
        response = await client.request(method, url, **kwargs)
    except httpx.TimeoutException:
        logger.error("Timeout: %s %s/%s", method, service, path)
        raise UpstreamTimeout()
    except httpx.RequestError:
        logger.error("Servicio inalcanzable: %s %s/%s", method, service, path)
        raise UpstreamUnreachable()

    logger.info("%s %s%s -> %s", method, service, path, response.status_code)
    return response
