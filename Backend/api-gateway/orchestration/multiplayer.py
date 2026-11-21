"""Flows REST de Multiplayer (contrato, sección 13). El gateway orquesta; Multiplayer es un hub.

Game Logic es la única fuente de verdad (estado, matchId, creationKey y requestFingerprint). El gateway
aplica aquí las reglas que antes aplicaba el servicio Go y, tras cada cambio, avisa al hub de Multiplayer
(POST /internal/multiplayer/matches/{id}/publish) para que actualice su sesión (plazos de reconexión) y lo
envíe por WebSocket. Ese aviso es de mejor esfuerzo: nunca falla la petición del usuario.

Los mensajes de error conservan el texto en inglés del servicio original.
"""

import hashlib
import json
import logging
import re
import uuid
from typing import Any

from . import upstream
from .context import Ctx
from .errors import FlowError, GatewayError, is_contract_error, payload_of

logger = logging.getLogger("gateway.web")

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
PUBLISH_TIMEOUT = 3.0  # el aviso al hub no debe retrasar la respuesta
# Errores de Game Logic tras los que el estado del hub pudo quedar atrasado: se relee y se publica
REFRESH_CODES = ("GAME_FINISHED", "GAME_NOT_IN_PROGRESS", "VERSION_CONFLICT", "CLOCK_EXPIRED")

MATCH_NOT_FOUND = "Match was not found"


def _error(status: int, code: str, message: str) -> FlowError:
    return FlowError(status, code, message)


class MoveRejected(FlowError):
    """Una jugada que Game Logic no aceptó (o que el gateway rechazó por la versión): al cliente se le
    responde con move_rejected en lugar de error."""


def _not_found() -> FlowError:
    return _error(404, "MATCH_NOT_FOUND", MATCH_NOT_FOUND)


def _lock(ctx: Ctx, match_id: str):
    return ctx.locks.get("match:" + match_id)


# ------------------------------------------------------- errores de Game Logic


def map_logic_error(response) -> FlowError:
    """Traduce un error de Game Logic como lo hacía el servicio de Multiplayer."""
    payload = payload_of(response)
    if is_contract_error(payload):
        code, message = payload["error"]["code"], payload["error"]["message"]
    else:
        code, message = "UPSTREAM_ERROR", "Game Logic returned an invalid error response"
    mapped = _map_logic_code(response.status_code, code, message)
    mapped.logic = (code, message)  # el error tal cual lo dio Game Logic (lo usan los frames WebSocket)
    return mapped


def _map_logic_code(status: int, code: str, message: str) -> FlowError:
    if code == "GAME_NOT_FOUND":
        return _error(404, "MATCH_NOT_FOUND", message)
    if code == "GAME_NOT_WAITING":
        return _error(409, "MATCH_NOT_WAITING", message)
    if code in ("ALREADY_PARTICIPANT", "IDEMPOTENCY_KEY_REUSED"):
        return _error(409, code, message)
    if status in (502, 503, 504):
        return _error(503, "SERVICES_UNAVAILABLE", "Game Logic is unavailable")
    return _error(status, code, message)


async def _logic(ctx: Ctx, method: str, path: str, *, json_body: Any = None):
    """Llama a Game Logic y devuelve (estado HTTP, GameState). Cualquier fallo es un FlowError."""
    try:
        response = await upstream.call(
            ctx.client, ctx.upstreams["logic"], "logic", method, path, json=json_body, timeout=ctx.timeout
        )
    except GatewayError:
        raise _error(503, "SERVICES_UNAVAILABLE", "Game Logic is unavailable")
    if not response.is_success:
        raise map_logic_error(response)
    state = payload_of(response)
    if not isinstance(state, dict) or not state.get("gameId") or not state.get("matchId"):
        raise _error(503, "SERVICES_UNAVAILABLE", "Game Logic is unavailable")
    return response.status_code, state


async def _load(ctx: Ctx, match_id: str) -> dict[str, Any]:
    """La partida de un matchId (Game Logic la resuelve con by-match). Siempre fresca."""
    if not UUID_RE.match(match_id):
        raise _not_found()
    _, state = await _logic(ctx, "GET", f"/games/by-match/{match_id}")
    if state.get("matchId") != match_id:
        raise _not_found()
    return state


def side_for(state: dict[str, Any], user_id: str) -> str | None:
    participants = state.get("participants")
    if not isinstance(participants, list):
        return None
    for participant in participants:
        if isinstance(participant, dict) and participant.get("userId") == user_id:
            return participant.get("color")
    return None


def is_finished(state: dict[str, Any]) -> bool:
    return state.get("status") == "finished" or state.get("result") is not None


# ------------------------------------------------------------------ hub (publish)


async def publish(
    ctx: Ctx,
    state: dict[str, Any],
    *,
    game_over: bool | None = None,
    events: list[dict[str, Any]] | None = None,
) -> None:
    """Avisa al hub de Multiplayer. Nunca lanza: un hub caído no debe fallar la petición. `events` son
    avisos de tablas que el hub envía después del state y antes de game_over."""
    match_id = state["matchId"]
    body: dict[str, Any] = {"state": state}
    if game_over is not None:
        body["gameOver"] = game_over
    if events:
        body["events"] = events
    try:
        response = await upstream.call(
            ctx.client, ctx.upstreams["multiplayer"], "multiplayer", "POST",
            f"/matches/{match_id}/publish", json=body, timeout=min(ctx.timeout, PUBLISH_TIMEOUT),
        )
        if response.status_code != 204:
            logger.warning("Multiplayer respondió %s al publicar la partida %s", response.status_code, match_id)
    except GatewayError:
        logger.warning("No se pudo avisar a Multiplayer de la partida %s", match_id)
    if is_finished(state):
        ctx.locks.drop("match:" + match_id)


async def _refresh_if_finished(ctx: Ctx, match_id: str, error: FlowError) -> None:
    """Tras un error que indica que el estado cambió, se relee la partida y se publica (state y, si terminó,
    game_over) para que el hub y los clientes no se queden con un estado viejo."""
    if error.code not in REFRESH_CODES:
        return
    try:
        state = await _load(ctx, match_id)
    except GatewayError as exc:
        logger.warning("No se pudo releer la partida %s: %s", match_id, exc.message)
        return
    await publish(ctx, state)


# ------------------------------------------------------------------ creación


def _invalid_body() -> FlowError:
    return _error(400, "VALIDATION_ERROR", "Invalid JSON request body")


def _strict_object(raw: bytes, allowed: set[str]) -> dict[str, Any]:
    """Cuerpo JSON de un solo valor, objeto y sin campos desconocidos (como el servicio original)."""
    try:
        body = json.loads(raw) if raw and raw.strip() else None
    except ValueError:
        body = None
    if not isinstance(body, dict) or not set(body) <= allowed:
        raise _invalid_body()
    return body


def _optional_string(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise _invalid_body()
    return value


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def creation_key(user_id: str, idempotency_key: str) -> str:
    return hashlib.sha256(f"{user_id}\n{idempotency_key}".encode()).hexdigest()


def request_fingerprint(creator_color: str, minutes: int, visibility: str) -> str:
    """Huella canónica del pedido ya con los valores por omisión aplicados (mismo JSON compacto que el
    servicio original, para que los reintentos de una creación anterior sigan siendo idempotentes)."""
    canonical = {"creatorColor": creator_color, "timeControl": {"minutes": minutes}, "visibility": visibility}
    return hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode()).hexdigest()


async def create(ctx: Ctx, user_id: str, idempotency_key: str, raw_body: bytes) -> tuple[dict[str, Any], bool]:
    """Crea la partida en Game Logic con la clave de creación y la huella: Game Logic garantiza la
    idempotencia de forma atómica. Devuelve (invitación, repetida)."""
    if not IDEMPOTENCY_KEY_RE.match(idempotency_key or ""):
        raise _error(400, "VALIDATION_ERROR", "Idempotency-Key must contain 1 to 128 valid characters")

    body = _strict_object(raw_body, {"timeControl", "visibility", "creatorColor"})
    color = _optional_string(body.get("creatorColor"))
    visibility = _optional_string(body.get("visibility"))
    time_control = body.get("timeControl")
    minutes = 10
    if time_control is not None:
        if not isinstance(time_control, dict) or not set(time_control) <= {"minutes"}:
            raise _invalid_body()
        raw_minutes = time_control.get("minutes")
        if raw_minutes is not None and not _is_int(raw_minutes):
            raise _invalid_body()
        minutes = raw_minutes or 0

    if color not in ("white", "black"):
        raise _error(400, "VALIDATION_ERROR", "creatorColor must be white or black")
    visibility = visibility or "private"
    if visibility not in ("private", "shared"):
        raise _error(400, "VALIDATION_ERROR", "visibility must be private or shared")
    if minutes < 1 or minutes > 10:
        raise _error(400, "VALIDATION_ERROR", "timeControl.minutes must be between 1 and 10")

    payload = {
        "mode": "multiplayer",
        "timeControl": {"minutes": minutes},
        "visibility": visibility,
        "botLevel": None,
        "matchId": str(uuid.uuid4()),
        "participants": [{"userId": user_id, "color": color}],
        "creationKey": creation_key(user_id, idempotency_key),
        "requestFingerprint": request_fingerprint(color, minutes, visibility),
    }
    status, state = await _logic(ctx, "POST", "/games", json_body=payload)
    if state.get("mode") != "multiplayer":
        raise _error(502, "UPSTREAM_ERROR", "Game Logic returned a non-multiplayer game")
    if not state.get("createdAt"):
        raise _error(502, "UPSTREAM_ERROR", "Game Logic returned an incomplete create response")
    invitation = {"matchId": state["matchId"], "status": "waiting", "createdAt": state["createdAt"]}
    return invitation, status == 200  # 200 de Game Logic = la creación ya existía


# ----------------------------------------------------------------- lectura


async def get(ctx: Ctx, user_id: str, match_id: str) -> dict[str, Any]:
    """Participante, o cualquiera si la partida es shared; si no, MATCH_NOT_FOUND."""
    state = await _load(ctx, match_id)
    if side_for(state, user_id) is None and state.get("visibility") != "shared":
        raise _not_found()
    return state


# -------------------------------------------------------------- unirse y acciones


async def join(ctx: Ctx, user_id: str, match_id: str) -> dict[str, Any]:
    async with _lock(ctx, match_id):
        state = await _load(ctx, match_id)
        if state.get("status") != "waiting":
            raise _error(409, "MATCH_NOT_WAITING", "Match is not waiting for an opponent")
        if side_for(state, user_id) is not None:
            raise _error(409, "ALREADY_PARTICIPANT", "The creator cannot join their own match")
        _, joined = await _logic(ctx, "POST", f"/games/{state['gameId']}/join", json_body={"userId": user_id})
        await publish(ctx, joined)
        return joined


async def resign(ctx: Ctx, user_id: str, match_id: str) -> dict[str, Any]:
    async with _lock(ctx, match_id):
        state = await _load(ctx, match_id)
        side = side_for(state, user_id)
        if side is None:
            raise _not_found()
        if state.get("status") != "in_progress":
            raise _error(409, "GAME_NOT_IN_PROGRESS", "Game is not in progress")
        try:
            _, nxt = await _logic(ctx, "POST", f"/games/{state['gameId']}/resign", json_body={"side": side})
        except FlowError as exc:
            await _refresh_if_finished(ctx, match_id, exc)
            raise
        await publish(ctx, nxt)  # state y, si terminó, game_over
        return nxt


async def change_visibility(ctx: Ctx, user_id: str, match_id: str, raw_body: bytes) -> dict[str, Any]:
    required = _error(400, "VALIDATION_ERROR", "visibility and expectedVersion are required")
    try:
        body = _strict_object(raw_body, {"visibility", "expectedVersion"})
    except FlowError:
        raise required
    expected = body.get("expectedVersion")
    if not _is_int(expected):
        raise required
    visibility = body.get("visibility")
    if visibility is not None and not isinstance(visibility, str):
        raise required
    if visibility not in ("private", "shared"):
        raise _error(400, "VALIDATION_ERROR", "visibility must be private or shared")

    async with _lock(ctx, match_id):
        state = await _load(ctx, match_id)
        if side_for(state, user_id) is None:
            raise _not_found()
        try:
            _, nxt = await _logic(
                ctx, "PATCH", f"/games/{state['gameId']}/visibility",
                json_body={"visibility": visibility, "expectedVersion": expected},
            )
        except FlowError as exc:
            await _refresh_if_finished(ctx, match_id, exc)
            raise
        # Sin game_over: cambiar la visibilidad no cambia el resultado de una partida ya terminada
        await publish(ctx, nxt, game_over=False)
        return nxt


# --------------------------------------------------------- acciones por WebSocket (frames)
# El hub ya no atiende move/resign/draw_*: llegan al gateway, que opera en Game Logic y publica el
# resultado. Los errores replican los mensajes del servicio original: una jugada rechazada por Game Logic es
# move_rejected con el código y el mensaje de Game Logic; todo lo demás es error.


def _logic_failure(exc: FlowError, *, move: bool) -> FlowError:
    """El error de una acción en Game Logic tal como lo vería el cliente por WebSocket."""
    logic = getattr(exc, "logic", None)
    if logic is None:  # Game Logic no respondió
        return _error(503, "SERVICES_UNAVAILABLE", "A required service is unavailable")
    code, message = logic
    return (MoveRejected if move else FlowError)(exc.status, code, message)


async def handle_move(ctx: Ctx, user_id: str, match_id: str, uci: Any, expected_version: Any) -> None:
    """Frame `move`. Lanza FlowError (error) o MoveRejected (move_rejected) si no se acepta."""
    if not isinstance(uci, str) or not uci.strip() or not _is_int(expected_version) or expected_version < 0:
        raise _error(400, "VALIDATION_ERROR", "move requires uci and expectedVersion")

    async with _lock(ctx, match_id):
        state = await _load(ctx, match_id)
        side = side_for(state, user_id)
        if side is None:
            raise _not_found()
        if state.get("status") != "in_progress" or is_finished(state):
            raise _error(409, "GAME_NOT_IN_PROGRESS", "Game is not in progress")
        if state.get("turn") != side:
            raise _error(422, "NOT_YOUR_TURN", "It is not your turn")
        if expected_version != state.get("version"):
            raise MoveRejected(409, "VERSION_CONFLICT", "Game state is out of date")

        try:
            _, nxt = await _logic(
                ctx, "POST", f"/games/{state['gameId']}/moves",
                json_body={"uci": uci.strip().lower(), "expectedVersion": expected_version},
            )
        except FlowError as exc:
            await _refresh_if_finished(ctx, match_id, exc)
            raise _logic_failure(exc, move=True)
        await publish(ctx, nxt)  # state y, si terminó, game_over


# operación de Game Logic, evento de aviso y regla previa de cada acción de tablas
_DRAWS = {
    "draw_offer": ("offer", "draw_offered"),
    "draw_accept": ("accept", None),
    "draw_decline": ("decline", "draw_declined"),
    "draw_cancel": ("cancel", "draw_cancelled"),
}
DRAW_FRAME_TYPES = tuple(_DRAWS)


def _draw_precheck(kind: str, state: dict[str, Any], side: str) -> None:
    offer = state.get("drawOffer")
    if kind == "draw_offer":
        if offer is not None:
            raise _error(409, "DRAW_ALREADY_OFFERED", "A draw offer is already pending")
    elif kind == "draw_accept":
        if offer is None or offer == side:
            raise _error(422, "DRAW_NOT_ALLOWED", "Only the opponent may accept a pending draw offer")
    elif kind == "draw_decline":
        if offer is None or offer == side:
            raise _error(422, "DRAW_NOT_ALLOWED", "Only the opponent may decline a pending draw offer")
    elif kind == "draw_cancel":
        if offer is None or offer != side:
            raise _error(422, "DRAW_NOT_ALLOWED", "Only the offer creator may cancel the draw offer")


async def handle_draw(ctx: Ctx, user_id: str, match_id: str, kind: str) -> None:
    """Frames `draw_offer`, `draw_accept`, `draw_decline` y `draw_cancel`."""
    operation, event_type = _DRAWS[kind]

    async with _lock(ctx, match_id):
        state = await _load(ctx, match_id)
        side = side_for(state, user_id)
        if side is None:
            raise _not_found()
        if state.get("status") != "in_progress":
            raise _error(409, "GAME_NOT_IN_PROGRESS", "Game is not in progress")
        _draw_precheck(kind, state, side)

        try:
            _, nxt = await _logic(
                ctx, "POST", f"/games/{state['gameId']}/draw/{operation}", json_body={"side": side}
            )
        except FlowError as exc:
            await _refresh_if_finished(ctx, match_id, exc)
            raise _logic_failure(exc, move=False)

        events = None
        if kind == "draw_offer":
            events = [{"type": event_type, "by": side}]
        elif event_type:
            events = [{"type": event_type}]
        await publish(ctx, nxt, events=events)  # state, el evento y, si terminó, game_over
