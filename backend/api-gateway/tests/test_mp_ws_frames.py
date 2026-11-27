"""Frames WebSocket de Multiplayer atendidos por el gateway (jugadas, rendición y tablas)."""

import asyncio
import json
import os
import time

os.environ.update(JWT_SECRET="x" * 40, WS_ALLOWED_ORIGINS="http://localhost")

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main
from main import app
from orchestration import multiplayer, ws_session
from orchestration.context import Ctx, GameLocks
from test_multiplayer_flows import A, B, C, GAME, MATCH, World, token
from test_ws_frames import FakeHub, wait_for

UPSTREAMS = {"logic": "http://logic", "multiplayer": "http://mp"}


def frame(**fields) -> str:
    return json.dumps(fields)


def run(world, *texts, user=A):
    """Procesa los frames como lo haría el trabajador de la conexión; devuelve lo enviado al cliente."""
    sent: list[dict] = []

    async def send(payload):
        sent.append(payload)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(world.handler)) as client:
            ctx = Ctx(client=client, upstreams=UPSTREAMS, locks=GameLocks(), timeout=5)
            for text in texts:
                await ws_session.handle_match_frame(ctx, user, MATCH, text, send)
            await ctx.tasks.drain(timeout=5)

    asyncio.run(go())
    return sent


def playing(world, **extra):
    """Partida en curso: A juega blancas y mueve primero; B juega negras."""
    fields = {"status": "in_progress", "version": 1,
              "participants": [{"userId": A, "color": "white"}, {"userId": B, "color": "black"}]}
    fields.update(extra)
    return world.add(**fields)


def rejected(code, message):
    return ws_session.rejected(code, message)


def error(code, message):
    return ws_session.error(code, message)


# ================================================================== jugadas


def test_a_move_is_applied_in_game_logic_and_published_without_replying_to_the_client():
    world = World()
    playing(world)
    sent = run(world, frame(type="move", uci="e2e4", expectedVersion=1))
    assert sent == []
    assert world.body(world.calls_to("/moves")[0]) == {"uci": "e2e4", "expectedVersion": 1}
    published = world.published()
    assert len(published) == 1 and published[0]["state"]["version"] == 2 and "events" not in published[0]
    assert published[0]["state"]["moves"][-1]["uci"] == "e2e4"
    assert all("x-user-id" not in c.headers for c in world.calls)


def test_the_uci_is_trimmed_and_lowercased_before_reaching_game_logic():
    world = World()
    playing(world)
    run(world, frame(type="move", uci="  E2E4 ", expectedVersion=1))
    assert world.body(world.calls_to("/moves")[0])["uci"] == "e2e4"


@pytest.mark.parametrize("message", [
    frame(type="move", expectedVersion=1), frame(type="move", uci="e2e4"), frame(type="move", uci="  ", expectedVersion=1),
    frame(type="move", uci="e2e4", expectedVersion=-1), frame(type="move", uci="e2e4", expectedVersion=None),
])
def test_incomplete_moves_are_an_error_without_calling_anyone(message):
    world = World()
    playing(world)
    assert run(world, message) == [error("VALIDATION_ERROR", "move requires uci and expectedVersion")]
    assert world.calls == []


def test_it_must_be_the_players_turn():
    world = World()
    playing(world)
    assert run(world, frame(type="move", uci="e7e5", expectedVersion=1), user=B) == [error("NOT_YOUR_TURN", "It is not your turn")]
    assert world.calls_to("/moves") == []


@pytest.mark.parametrize("status", ["waiting", "finished"])
def test_moves_need_a_game_in_progress(status):
    world = World()
    playing(world, status=status)
    assert run(world, frame(type="move", uci="e2e4", expectedVersion=1)) == [error("GAME_NOT_IN_PROGRESS", "Game is not in progress")]
    assert world.calls_to("/moves") == []


def test_a_result_also_means_not_in_progress():
    world = World()
    playing(world, result="1-0")
    assert run(world, frame(type="move", uci="e2e4", expectedVersion=1))[0]["code"] == "GAME_NOT_IN_PROGRESS"


def test_non_participants_get_match_not_found_as_an_error():
    world = World()
    playing(world)
    assert run(world, frame(type="move", uci="e2e4", expectedVersion=1), user=C) == [error("MATCH_NOT_FOUND", "Match was not found")]
    assert run(world, frame(type="draw_offer"), user=C) == [error("MATCH_NOT_FOUND", "Match was not found")]
    assert world.calls_to("/moves") == [] and world.calls_to("/draw/offer") == []


def test_a_stale_version_is_move_rejected_before_calling_game_logic():
    world = World()
    playing(world, version=5)
    assert run(world, frame(type="move", uci="e2e4", expectedVersion=4)) == [rejected("VERSION_CONFLICT", "Game state is out of date")]
    assert world.calls_to("/moves") == [] and world.published() == []


def test_game_logic_rejections_are_move_rejected_with_their_own_code_and_message():
    world = World()
    playing(world)
    assert run(world, frame(type="move", uci="e2e5", expectedVersion=1)) == [rejected("INVALID_MOVE", "Jugada ilegal")]
    assert world.published() == []  # un código ajeno al estado no publica nada


@pytest.mark.parametrize("logic_code, status", [("GAME_FINISHED", 422), ("VERSION_CONFLICT", 409), ("CLOCK_EXPIRED", 422)])
def test_a_move_that_races_with_a_finish_publishes_the_real_state_and_then_rejects(logic_code, status):
    world = World()
    playing(world)
    original = world.logic

    def raced(method, path, body):
        if path.endswith("/moves"):
            world.games[GAME].update(status="finished", result="0-1", endReason="timeout", version=7)
            return httpx.Response(status, json={"error": {"code": logic_code, "message": "perdiste la carrera"}})
        return original(method, path, body)

    world.logic = raced
    sent = run(world, frame(type="move", uci="e2e4", expectedVersion=1))
    assert sent == [rejected(logic_code, "perdiste la carrera")]
    published = world.published()
    assert len(published) == 1 and published[0]["state"]["status"] == "finished" and published[0]["state"]["version"] == 7


@pytest.mark.parametrize("reply", [(503, {"error": {"code": "X", "message": "caído"}}), (500, None)])
def test_game_logic_5xx_on_a_move_keeps_the_original_behaviour_move_rejected_with_its_code(reply):
    """El servicio original respondía move_rejected con el código de Game Logic aunque fuera un 5xx; solo un
    fallo de red era `error` SERVICES_UNAVAILABLE."""
    world = World()
    playing(world)
    original = world.logic
    status, payload = reply
    world.logic = lambda m, p, b: (
        httpx.Response(status, json=payload) if payload is not None else httpx.Response(status, text="x")
    ) if p.endswith("/moves") else original(m, p, b)
    sent = run(world, frame(type="move", uci="e2e4", expectedVersion=1))
    assert len(sent) == 1 and sent[0]["type"] == "move_rejected"
    assert sent[0]["code"] in ("X", "UPSTREAM_ERROR")


@pytest.mark.parametrize("failure", [httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_game_logic_unreachable_is_an_error_services_unavailable(failure):
    world = World()
    playing(world)

    async def boom(request):
        raise failure

    world.handler = boom
    sent = run(world, frame(type="move", uci="e2e4", expectedVersion=1))
    assert len(sent) == 1 and sent[0]["type"] == "error" and sent[0]["code"] == "SERVICES_UNAVAILABLE"


def test_a_failure_during_the_move_itself_is_services_unavailable():
    world = World()
    playing(world)
    original = world.handler

    async def flaky(request):
        if request.url.path.endswith("/moves"):
            raise httpx.ReadTimeout("lento")
        return await original(request)

    world.handler = flaky
    assert run(world, frame(type="move", uci="e2e4", expectedVersion=1)) == [error("SERVICES_UNAVAILABLE", "A required service is unavailable")]


# ================================================================== rendirse


def test_resign_by_frame_uses_the_same_flow_as_rest_and_publishes_the_final_state():
    world = World()
    playing(world)
    sent = run(world, frame(type="resign"), user=B)
    assert sent == []
    assert world.body(world.calls_to("/resign")[0]) == {"side": "black"}
    published = world.published()
    assert len(published) == 1 and published[0]["state"]["status"] == "finished"


@pytest.mark.parametrize("status, code, message", [
    ("waiting", "GAME_NOT_IN_PROGRESS", "Game is not in progress"),
    ("finished", "GAME_NOT_IN_PROGRESS", "Game is not in progress"),
])
def test_resign_errors_are_sent_as_error(status, code, message):
    world = World()
    playing(world, status=status)
    assert run(world, frame(type="resign")) == [error(code, message)]


def test_non_participants_cannot_resign_by_frame():
    world = World()
    playing(world)
    assert run(world, frame(type="resign"), user=C) == [error("MATCH_NOT_FOUND", "Match was not found")]


# ================================================================== tablas


def hub_events(world):
    return [p.get("events") for p in world.published()]


def test_offering_a_draw_publishes_the_state_and_a_draw_offered_event_with_the_side():
    world = World()
    playing(world)
    assert run(world, frame(type="draw_offer")) == []
    assert world.body(world.calls_to("/draw/offer")[0]) == {"side": "white"}
    published = world.published()[0]
    assert published["state"]["drawOffer"] == "white" and published["events"] == [{"type": "draw_offered", "by": "white"}]


def test_the_opponent_can_accept_and_the_game_finishes_without_an_extra_event():
    world = World()
    playing(world, drawOffer="white")
    assert run(world, frame(type="draw_accept"), user=B) == []
    assert world.body(world.calls_to("/draw/accept")[0]) == {"side": "black"}
    published = world.published()[0]
    assert published["state"]["status"] == "finished" and "events" not in published and "gameOver" not in published


def test_the_opponent_can_decline_and_the_offer_creator_can_cancel():
    world = World()
    playing(world, drawOffer="white")
    run(world, frame(type="draw_decline"), user=B)
    assert hub_events(world) == [[{"type": "draw_declined"}]]
    world.published().clear()
    run(world, frame(type="draw_offer"))
    run(world, frame(type="draw_cancel"))
    assert world.published()[-1]["events"] == [{"type": "draw_cancelled"}]


@pytest.mark.parametrize("frame_type, user, offer, code, message, status", [
    ("draw_offer", A, "black", "DRAW_ALREADY_OFFERED", "A draw offer is already pending", None),
    ("draw_accept", A, None, "DRAW_NOT_ALLOWED", "Only the opponent may accept a pending draw offer", None),
    ("draw_accept", A, "white", "DRAW_NOT_ALLOWED", "Only the opponent may accept a pending draw offer", None),
    ("draw_decline", A, None, "DRAW_NOT_ALLOWED", "Only the opponent may decline a pending draw offer", None),
    ("draw_decline", A, "white", "DRAW_NOT_ALLOWED", "Only the opponent may decline a pending draw offer", None),
    ("draw_cancel", A, None, "DRAW_NOT_ALLOWED", "Only the offer creator may cancel the draw offer", None),
    ("draw_cancel", A, "black", "DRAW_NOT_ALLOWED", "Only the offer creator may cancel the draw offer", None),
    ("draw_offer", A, None, "GAME_NOT_IN_PROGRESS", "Game is not in progress", "waiting"),
])
def test_draw_prechecks_are_errors_and_never_reach_game_logic(frame_type, user, offer, code, message, status):
    world = World()
    extra = {"drawOffer": offer}
    if status:
        extra["status"] = status
    playing(world, **extra)
    assert run(world, frame(type=frame_type), user=user) == [error(code, message)]
    assert [c for c in world.calls if "/draw/" in c.url.path] == [] and world.published() == []


def test_a_draw_that_races_with_a_finish_publishes_the_real_state_and_sends_the_error():
    world = World()
    playing(world)
    original = world.logic

    def raced(method, path, body):
        if "/draw/" in path:
            world.games[GAME].update(status="finished", result="1-0", endReason="resignation", version=9)
            return httpx.Response(422, json={"error": {"code": "GAME_FINISHED", "message": "ya terminó"}})
        return original(method, path, body)

    world.logic = raced
    assert run(world, frame(type="draw_offer")) == [error("GAME_FINISHED", "ya terminó")]  # `error`, no move_rejected
    published = world.published()
    assert len(published) == 1 and published[0]["state"]["version"] == 9 and "events" not in published[0]


def test_draw_logic_errors_are_sent_as_error_with_their_code():
    world = World()
    playing(world)
    original = world.logic
    world.logic = lambda m, p, b: (
        httpx.Response(422, json={"error": {"code": "DRAW_NOT_ALLOWED", "message": "no se puede"}}) if "/draw/" in p else original(m, p, b)
    )
    assert run(world, frame(type="draw_offer")) == [error("DRAW_NOT_ALLOWED", "no se puede")]


# ================================================================== frames inválidos


@pytest.mark.parametrize("text", [
    "{no es json", "[1, 2]", "5", '"x"', frame(type=5), frame(type="move", uci=5, expectedVersion=1),
    frame(type="move", uci="e2e4", expectedVersion="1"), frame(type="move", uci="e2e4", expectedVersion=1.5),
    frame(type="move", uci="e2e4", expectedVersion=True),
])
def test_wrong_json_types_are_invalid_json_message(text):
    world = World()
    playing(world)
    assert run(world, text) == [error("VALIDATION_ERROR", "Invalid JSON message")]
    assert world.calls == []


@pytest.mark.parametrize("text", [frame(uci="e2e4"), frame(type="hacer_trampa"), frame(type=""), frame(type="PING")])
def test_unknown_or_missing_types_are_unknown_message_type(text):
    world = World()
    playing(world)
    assert run(world, text) == [error("VALIDATION_ERROR", "Unknown message type")]
    assert world.calls == []


def test_unexpected_exceptions_become_internal_error(monkeypatch):
    world = World()
    playing(world)

    async def boom(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(multiplayer, "handle_move", boom)
    assert run(world, frame(type="move", uci="e2e4", expectedVersion=1)) == [error("INTERNAL_ERROR", "Error interno del servidor")]


def test_is_ping_only_for_a_ping_object():
    assert ws_session.is_ping('{"type":"ping"}') and ws_session.is_ping(' {"type": "ping", "x": 1} ')
    assert not any(ws_session.is_ping(t) for t in ('{"type":"move"}', "no json", "[1]", "5", '{"type":"Ping"}'))


# ================================================================== orden


def test_frames_of_a_connection_are_processed_in_order_with_a_single_worker():
    world = World()
    playing(world)
    world.delay = 0.02
    sent: list[dict] = []

    async def send(payload):
        sent.append(payload)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(world.handler)) as client:
            ctx = Ctx(client=client, upstreams=UPSTREAMS, locks=GameLocks(), timeout=5)
            queue, task = ws_session.start_frame_worker(ctx, A, MATCH, send, match=True)
            queue.put_nowait(frame(type="move", uci="e2e4", expectedVersion=1))
            queue.put_nowait(frame(type="move", uci="e7e5", expectedVersion=2))
            queue.put_nowait(frame(type="move", uci="g1f3", expectedVersion=3))
            queue.put_nowait(None)
            await task

    asyncio.run(go())
    # A juega blancas: tras e2e4 es el turno de las negras, así que la 2.ª y la 3.ª se rechazan, en orden
    assert sent == [error("NOT_YOUR_TURN", "It is not your turn")] * 2
    assert [world.body(c)["uci"] for c in world.calls_to("/moves")] == ["e2e4"]


# ================================================================== proxy con un hub WebSocket real


@pytest.fixture
def live(monkeypatch):
    world = World()
    hub = FakeHub()
    monkeypatch.setitem(main.UPSTREAMS, "multiplayer", hub.url)
    with TestClient(app) as client:
        app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(world.handler))
        client.cookies.set("session", token(A))
        yield client, world, hub
    hub.close()


def connect(client):
    return client.websocket_connect(f"/ws/matches/{MATCH}", headers={"origin": "http://localhost"})


def test_the_gateway_applies_moves_and_answers_errors_while_the_hub_only_sees_the_ping(live):
    client, world, hub = live
    playing(world)
    with connect(client) as ws:
        assert ws.receive_json()["type"] == "state"  # del hub
        ws.send_text(frame(type="move", uci="e2e4", expectedVersion=1))
        assert wait_for(lambda: world.calls_to("/moves"))
        ws.send_text(frame(type="move", uci="e7e5", expectedVersion=2))  # turno de B
        assert ws.receive_json() == error("NOT_YOUR_TURN", "It is not your turn")
        ws.send_text(frame(type="draw_cancel"))
        assert ws.receive_json()["code"] == "DRAW_NOT_ALLOWED"
        ws.send_text(frame(type="ping"))
        assert wait_for(lambda: hub.received)
    assert hub.received == [frame(type="ping")] and hub.user_ids == [A]
    assert world.games[GAME]["version"] == 2


def test_a_move_in_flight_still_completes_if_the_client_disconnects(live):
    client, world, hub = live
    playing(world)
    world.delay = 0.3
    with connect(client) as ws:
        ws.receive_json()
        ws.send_text(frame(type="move", uci="e2e4", expectedVersion=1))
    assert wait_for(lambda: world.published())
    assert world.games[GAME]["version"] == 2 and world.published()[0]["state"]["moves"][-1]["uci"] == "e2e4"


def test_a_draw_offer_by_frame_publishes_its_event(live):
    client, world, hub = live
    playing(world)
    with connect(client) as ws:
        ws.receive_json()
        ws.send_text(frame(type="draw_offer"))
        assert wait_for(lambda: world.published())
    assert world.published()[0]["events"] == [{"type": "draw_offered", "by": "white"}]


def test_the_hub_still_authorizes_the_connection(live):
    client, world, hub = live
    # el gateway no conoce a los participantes al conectar: el cierre 4404 lo da el hub; aquí, partida inexistente
    # no cambia nada porque FakeHub acepta: lo que importa es que el gateway no rompe el flujo de cierre
    client.cookies.set("session", token(B))
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws/matches/no-es-uuid", headers={"origin": "http://localhost"}) as ws:
            ws.receive_text()
    assert e.value.code == 4404 and not hub.connected.is_set()
