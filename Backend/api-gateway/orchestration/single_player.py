"""Flows de Single Player (contrato, sección 12). El gateway orquesta; Single Player es un hub.

Game Logic es la única fuente de verdad. Aquí se decide quién participa y de quién es el turno (a partir
de participants), se pide la jugada a Botcito y, tras cada cambio, se avisa al hub de Single Player
(POST /internal/single-player/games/{id}/publish) para que lo envíe por WebSocket a los clientes.

El aviso al hub es de mejor esfuerzo: si falla se registra, pero nunca falla la petición del usuario
(la respuesta REST es la verdad y el cliente puede releer la partida).
"""

import json
import logging
from typing import Any

from . import engine, logic, upstream
from .context import Ctx
from .errors import FlowError, GatewayError

logger = logging.getLogger("gateway.web")

LOCAL = "local"
VS_BOT = "vs_bot"
PRIVATE = "private"
SHARED = "shared"
ALLOWED_MINUTES = 10  # único control de tiempo permitido
PUBLISH_TIMEOUT = 3.0  # el aviso al hub no debe retrasar la respuesta

NOT_FOUND = "La partida no existe o no es visible"


# ------------------------------------------------------------------ entrada


def _validation(message: str) -> FlowError:
    return FlowError(400, "VALIDATION_ERROR", message)


def _json_object(raw: bytes) -> dict[str, Any]:
    if not raw or not raw.strip():
        raise _validation("Falta el cuerpo de la petición")
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise _validation("El cuerpo de la petición no es un JSON válido")
    return body


def _is_color(value: Any) -> bool:
    return value in ("white", "black")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ----------------------------------------------------------- reglas de juego


def _participants(state: dict[str, Any]) -> list[dict[str, Any]]:
    participants = state.get("participants")
    if not isinstance(participants, list):
        return []
    return [p for p in participants if isinstance(p, dict)]


def is_participant(state: dict[str, Any], user_id: str) -> bool:
    return any(p.get("userId") == user_id for p in _participants(state))


def human_color(state: dict[str, Any]) -> str | None:
    """Color del humano en vs_bot: el de su única entrada en participants. None si la partida no es
    vs_bot o no respeta esa cardinalidad."""
    participants = _participants(state)
    if state.get("mode") != VS_BOT or len(participants) != 1:
        return None
    return participants[0].get("color")


def is_finished(state: dict[str, Any]) -> bool:
    return state.get("status") == "finished"


def is_bot_turn(state: dict[str, Any]) -> bool:
    """Turno del bot: vs_bot en curso y el turno no es el del humano."""
    human = human_color(state)
    return human is not None and state.get("status") == "in_progress" and state.get("turn") != human


def last_uci(state: dict[str, Any]) -> str | None:
    moves = state.get("moves")
    if not isinstance(moves, list) or not moves or not isinstance(moves[-1], dict):
        return None
    return moves[-1].get("uci")


# -------------------------------------------------------------- hub (publish)


async def publish(
    ctx: Ctx,
    game_id: str,
    *,
    state: dict[str, Any] | None = None,
    last_move: str | None = None,
    game_over: bool | None = None,
    signal: dict[str, str] | None = None,
) -> None:
    """Avisa al hub de Single Player. Nunca lanza: un hub caído no debe fallar la petición."""
    body: dict[str, Any] = {}
    if state is not None:
        body["state"] = state
    if last_move is not None:
        body["lastMove"] = last_move
    if game_over is not None:
        body["gameOver"] = game_over
    if signal is not None:
        body["signal"] = signal
    try:
        response = await upstream.call(
            ctx.client, ctx.upstreams["single-player"], "single-player", "POST",
            f"/games/{game_id}/publish", json=body, timeout=min(ctx.timeout, PUBLISH_TIMEOUT),
        )
        if response.status_code != 204:
            logger.warning("Single Player respondió %s al publicar la partida %s", response.status_code, game_id)
    except GatewayError:
        logger.warning("No se pudo avisar a Single Player de la partida %s", game_id)


async def publish_state(ctx: Ctx, state: dict[str, Any], last_move: str | None = None, **kwargs) -> None:
    await publish(ctx, state["gameId"], state=state, last_move=last_move, **kwargs)
    if is_finished(state):
        ctx.locks.drop(state["gameId"])


# ------------------------------------------------------------------ lectura


async def _single_player_game(ctx: Ctx, game_id: str) -> dict[str, Any]:
    """La partida debe existir y ser local o vs_bot; las multijugador no son de Single Player."""
    state = await logic.fetch_game(ctx.client, ctx.upstreams, game_id, timeout=ctx.timeout)
    if state.get("mode") not in (LOCAL, VS_BOT):
        raise FlowError(404, "GAME_NOT_FOUND", NOT_FOUND)
    return state


async def participant_game(ctx: Ctx, user_id: str, game_id: str) -> dict[str, Any]:
    """Partida local o vs_bot en la que el usuario participa (acciones y WebSocket); si no, 404."""
    state = await _single_player_game(ctx, game_id)
    if not is_participant(state, user_id):
        raise FlowError(404, "GAME_NOT_FOUND", NOT_FOUND)
    return state


_participant_game = participant_game


async def get_game(ctx: Ctx, user_id: str, game_id: str) -> dict[str, Any]:
    """Lectura: participante o partida shared."""
    state = await _single_player_game(ctx, game_id)
    if not is_participant(state, user_id) and state.get("visibility") != SHARED:
        raise FlowError(404, "GAME_NOT_FOUND", NOT_FOUND)
    return state


# ----------------------------------------------------------------- creación


async def create(ctx: Ctx, user_id: str, raw_body: bytes) -> dict[str, Any]:
    """Arma el cuerpo de Game Logic según el modo: en local dos participantes con el mismo userId, uno
    por color; en vs_bot uno solo, el humano. Si el bot abre y falla, la partida se devuelve igual."""
    body = _json_object(raw_body)
    mode = body.get("mode")
    bot_level = None

    if mode == VS_BOT:
        bot_level = body.get("botLevel")
        if not _is_int(bot_level) or not 1 <= bot_level <= 20:
            raise _validation("botLevel debe ser un entero de 1 a 20")
        color = body.get("playerColor")
        if not _is_color(color):
            raise _validation('playerColor debe ser "white" o "black"')
        participants = [{"userId": user_id, "color": color}]
    elif mode == LOCAL:
        participants = [{"userId": user_id, "color": "white"}, {"userId": user_id, "color": "black"}]
    else:
        raise _validation('mode debe ser "local" o "vs_bot"')

    time_control = body.get("timeControl")
    if time_control is not None and not (
        isinstance(time_control, dict) and time_control.get("minutes") == ALLOWED_MINUTES
        and _is_int(time_control.get("minutes"))
    ):
        raise _validation('timeControl debe ser null o { "minutes": 10 }')

    visibility = PRIVATE if body.get("visibility") is None else body.get("visibility")
    if visibility not in (PRIVATE, SHARED):
        raise _validation('visibility debe ser "private" o "shared"')

    state = await logic.create_game(
        ctx.client, ctx.upstreams,
        {"mode": mode, "timeControl": time_control, "visibility": visibility,
         "botLevel": bot_level, "participants": participants},
        timeout=ctx.timeout,
    )

    # Si el jugador eligió negras, el bot abre la partida antes de responder.
    if is_bot_turn(state):
        async with ctx.locks.get(state["gameId"]):
            state = await try_bot_turn(ctx, state)
    return state


# ------------------------------------------------------------ turno del bot


async def bot_turn(ctx: Ctx, state: dict[str, Any]) -> dict[str, Any]:
    """Pide la jugada a Botcito y la aplica en Game Logic. Lanza FlowError si algo falla."""
    game_id = state["gameId"]
    await publish(ctx, game_id, signal={"type": "bot_thinking"})

    best = await engine.best_move(
        ctx.client, ctx.upstreams, state.get("fen"), state.get("botLevel"), timeout=ctx.timeout
    )
    nxt = await logic.move(ctx.client, ctx.upstreams, game_id, best["uci"], state["version"], timeout=ctx.timeout)
    await publish_state(ctx, nxt, last_uci(nxt))
    return nxt


async def try_bot_turn(ctx: Ctx, state: dict[str, Any]) -> dict[str, Any]:
    """Igual que bot_turn, pero si falla avisa a los clientes y deja la partida como estaba."""
    try:
        return await bot_turn(ctx, state)
    except GatewayError as exc:
        logger.warning("El turno del bot falló en la partida %s: %s", state.get("gameId"), exc.message)
        await publish(ctx, state["gameId"], signal={"type": "error", "code": exc.code, "message": exc.message})
        return state


# ------------------------------------------------------- rendición y visibilidad


async def resign(ctx: Ctx, user_id: str, game_id: str, raw_body: bytes) -> dict[str, Any]:
    """Rendición por REST: side solo hace falta en modo local; en vs_bot se usa el color del humano."""
    requested = None
    if raw_body and raw_body.strip():
        requested = _json_object(raw_body).get("side")
    return await resign_side(ctx, user_id, game_id, requested)


async def resign_side(ctx: Ctx, user_id: str, game_id: str, requested: Any) -> dict[str, Any]:
    async with ctx.locks.get(game_id):
        state = await participant_game(ctx, user_id, game_id)
        if state.get("mode") == VS_BOT:
            side = human_color(state)
        else:
            if not _is_color(requested):
                raise _validation('side debe ser "white" o "black" en modo local')
            side = requested

        nxt = await logic.resign(ctx.client, ctx.upstreams, game_id, side, timeout=ctx.timeout)
        await publish_state(ctx, nxt)
        return nxt


async def change_visibility(ctx: Ctx, user_id: str, game_id: str, raw_body: bytes) -> dict[str, Any]:
    """Cambia la visibilidad. Una versión vieja responde 409 VERSION_CONFLICT desde Game Logic."""
    body = _json_object(raw_body)
    visibility = body.get("visibility")
    if visibility not in (PRIVATE, SHARED):
        raise _validation('visibility debe ser "private" o "shared"')
    expected = body.get("expectedVersion")
    if not _is_int(expected):
        raise _validation("Falta el campo expectedVersion")

    async with ctx.locks.get(game_id):
        await _participant_game(ctx, user_id, game_id)
        nxt = await logic.set_visibility(ctx.client, ctx.upstreams, game_id, visibility, expected, timeout=ctx.timeout)
        # La versión subió: las sesiones abiertas necesitan el state nuevo para seguir jugando
        # (sin game_over: aunque la partida esté terminada, no cambió su resultado).
        await publish_state(ctx, nxt, game_over=False)
        return nxt


# --------------------------------------------------------------- jugadas (frames WebSocket)


async def resync(ctx: Ctx, game_id: str) -> None:
    """Reenvía el estado actual a las sesiones abiertas; si no se puede leer, no hace nada."""
    try:
        state = await logic.fetch_game(ctx.client, ctx.upstreams, game_id, timeout=ctx.timeout)
    except GatewayError as exc:
        logger.warning("No se pudo releer la partida %s: %s", game_id, exc.message)
        return
    await publish_state(ctx, state)


async def handle_move(ctx: Ctx, user_id: str, game_id: str, uci: Any, expected_version: Any) -> None:
    """Jugada del humano (frame `move`). Todo lo que cambia se publica a los clientes conectados; si es
    el turno del bot, se le pide su jugada a continuación. Lanza FlowError si la jugada no se acepta."""
    if not isinstance(uci, str) or not uci.strip():
        raise _validation("Falta el campo uci")
    if not _is_int(expected_version):
        raise _validation("Falta el campo expectedVersion")

    async with ctx.locks.get(game_id):
        state = await participant_game(ctx, user_id, game_id)
        if is_finished(state):
            raise FlowError(422, "GAME_FINISHED", "La partida ya terminó")
        if state.get("mode") == VS_BOT and state.get("turn") != human_color(state):
            raise FlowError(422, "NOT_YOUR_TURN", "No es tu turno")

        try:
            nxt = await logic.move(ctx.client, ctx.upstreams, game_id, uci, expected_version, timeout=ctx.timeout)
        except FlowError as exc:
            # El cliente tenía un estado viejo, o el reloj venció y la partida terminó: se le envía el
            # state actual (y game_over si terminó) antes del move_rejected
            if exc.code in ("VERSION_CONFLICT", "CLOCK_EXPIRED"):
                await resync(ctx, game_id)
            raise
        await publish_state(ctx, nxt, last_uci(nxt))

        if is_bot_turn(nxt):
            await try_bot_turn(ctx, nxt)


async def resume_bot_if_needed(ctx: Ctx, state: dict[str, Any]) -> None:
    """Si al conectarse un cliente le toca mover al bot (p. ej. Botcito estaba caído cuando se creó la
    partida o tras la jugada humana), se retoma su turno. Pensado para correr en segundo plano."""
    if not is_bot_turn(state):
        return
    game_id = state["gameId"]
    async with ctx.locks.get(game_id):
        try:
            fresh = await logic.fetch_game(ctx.client, ctx.upstreams, game_id, timeout=ctx.timeout)
            if is_bot_turn(fresh):
                await bot_turn(ctx, fresh)
        except GatewayError as exc:
            await publish(ctx, game_id, signal={"type": "error", "code": exc.code, "message": exc.message})
