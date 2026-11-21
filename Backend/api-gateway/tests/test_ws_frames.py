"""Frames WebSocket de Single Player atendidos por el gateway (jugadas, rendición, turno del bot)."""

import asyncio
import json
import os
import threading
import time

os.environ.update(JWT_SECRET="x" * 40, WS_ALLOWED_ORIGINS="http://localhost")

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from websockets.sync.server import serve

import main
from main import app
from orchestration import single_player, ws_session
from orchestration.context import Ctx, GameLocks
from test_single_player_flows import A, B, GID, World, token

UPSTREAMS = {"logic": "http://logic", "engine": "http://engine", "single-player": "http://sp"}


def frame(**fields) -> str:
    return json.dumps(fields)


def run(world, scenario):
    """Ejecuta `scenario(ctx, sent)` con servicios simulados; devuelve lo enviado al cliente."""
    sent: list[dict] = []

    async def send(payload):
        sent.append(payload)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(world.handler)) as client:
            ctx = Ctx(client=client, upstreams=UPSTREAMS, locks=GameLocks(), timeout=5)
            await scenario(ctx, send)
            await ctx.tasks.drain(timeout=5)

    asyncio.run(go())
    return sent


def frames(world, *texts, user=A):
    async def scenario(ctx, send):
        for text in texts:
            await ws_session.handle_frame(ctx, user, GID, text, send)

    return run(world, scenario)


def hub_types(world):
    return [("signal:" + p["signal"]["type"]) if "signal" in p else "state" for p in world.published()]


def vs_bot(world, human="white", turn="white", **extra):
    return world.add(mode="vs_bot", participants=[{"userId": A, "color": human}], botLevel=5, turn=turn, **extra)


# ================================================================== jugadas


def test_a_local_move_is_applied_in_game_logic_and_published_to_the_hub():
    world = World()
    world.add()
    sent = frames(world, frame(type="move", uci="e2e4", expectedVersion=0))
    assert sent == []  # lo que cambia llega al cliente por el hub, no por el gateway
    assert world.body(world.calls_to("/moves")[0]) == {"uci": "e2e4", "expectedVersion": 0}
    published = world.published()
    assert len(published) == 1 and published[0]["lastMove"] == "e2e4" and published[0]["state"]["version"] == 1
    assert world.calls_to("/best-move") == []


def test_human_move_in_a_bot_game_is_followed_by_the_bots_turn():
    world = World()
    vs_bot(world, human="white", turn="white")
    sent = frames(world, frame(type="move", uci="e2e4", expectedVersion=0))
    assert sent == []
    assert world.body(world.calls_to("/best-move")[0]) == {"fen": "fen-0", "botLevel": 5}
    assert [world.body(c)["expectedVersion"] for c in world.calls_to("/moves")] == [0, 1]
    assert hub_types(world) == ["state", "signal:bot_thinking", "state"]
    assert world.published()[-1]["lastMove"] == "e7e5" and world.published()[-1]["state"]["version"] == 2


def test_a_bot_failure_keeps_the_human_move_and_warns_with_the_real_code():
    world = World()
    vs_bot(world)
    world.engine_error = (504, "ENGINE_TIMEOUT")
    sent = frames(world, frame(type="move", uci="e2e4", expectedVersion=0))
    assert sent == []  # no se rechaza la jugada humana: ya está guardada
    assert hub_types(world) == ["state", "signal:bot_thinking", "signal:error"]
    assert world.published()[-1]["signal"]["code"] == "ENGINE_TIMEOUT"
    assert world.games[GID]["version"] == 1


@pytest.mark.parametrize("text, message", [
    (frame(type="move", expectedVersion=0), "Falta el campo uci"),
    (frame(type="move", uci=" ", expectedVersion=0), "Falta el campo uci"),
    (frame(type="move", uci=5, expectedVersion=0), "Falta el campo uci"),
    (frame(type="move", uci="e2e4"), "Falta el campo expectedVersion"),
    (frame(type="move", uci="e2e4", expectedVersion="0"), "Falta el campo expectedVersion"),
])
def test_incomplete_moves_are_rejected_without_calling_anyone(text, message):
    world = World()
    world.add()
    sent = frames(world, text)
    assert sent == [ws_session.rejected("VALIDATION_ERROR", message)]
    assert world.calls == []


@pytest.mark.parametrize("text, message", [
    ("{no es json", "El mensaje no es un JSON válido"),
    ("[1, 2]", "El mensaje no es un JSON válido"),
    ("5", "El mensaje no es un JSON válido"),
    (frame(uci="e2e4"), "Falta el campo type"),
    (frame(type="hacer_trampa"), "Tipo de mensaje desconocido: hacer_trampa"),
])
def test_bad_frames_are_rejected(text, message):
    world = World()
    world.add()
    sent = frames(world, text)
    assert sent == [ws_session.rejected("VALIDATION_ERROR", message)]
    assert world.calls == []


def test_version_conflict_sends_the_current_state_to_the_hub_before_rejecting():
    world = World()
    world.add(version=8, turn="black")
    sent = frames(world, frame(type="move", uci="e2e4", expectedVersion=7))
    assert sent == [ws_session.rejected("VERSION_CONFLICT", "versión distinta")]
    assert hub_types(world) == ["state"]
    assert world.published()[0]["state"]["version"] == 8 and "lastMove" not in world.published()[0]


def test_clock_expired_resyncs_the_final_state_and_lets_the_hub_announce_game_over():
    world = World()
    world.add(version=2)
    original = world.logic

    def clock(method, path, body):
        if path.endswith("/moves"):
            world.games[GID].update(status="finished", result="black", endReason="timeout", version=3)
            return httpx.Response(422, json={"error": {"code": "CLOCK_EXPIRED", "message": "Reloj vencido"}})
        return original(method, path, body)

    world.logic = clock
    sent = frames(world, frame(type="move", uci="e2e4", expectedVersion=2))
    assert sent == [ws_session.rejected("CLOCK_EXPIRED", "Reloj vencido")]
    state = world.published()[0]
    assert state["state"]["status"] == "finished" and "gameOver" not in state  # el hub envia game_over


def test_moving_on_the_bots_turn_is_not_your_turn():
    world = World()
    vs_bot(world, human="white", turn="black", version=1)
    sent = frames(world, frame(type="move", uci="e7e5", expectedVersion=1))
    assert sent == [ws_session.rejected("NOT_YOUR_TURN", "No es tu turno")]
    assert world.calls_to("/moves") == []


def test_moving_on_a_finished_game_is_game_finished():
    world = World()
    world.add(status="finished", result="black", endReason="surrender", version=4)
    sent = frames(world, frame(type="move", uci="e2e4", expectedVersion=4))
    assert sent == [ws_session.rejected("GAME_FINISHED", "La partida ya terminó")]
    assert world.calls_to("/moves") == []


def test_logic_rejections_keep_their_code_as_move_rejected():
    world = World()
    world.add()
    original = world.logic
    world.logic = lambda m, p, b: (
        httpx.Response(422, json={"error": {"code": "INVALID_MOVE", "message": "Jugada ilegal"}})
        if p.endswith("/moves") else original(m, p, b)
    )
    assert frames(world, frame(type="move", uci="e2e5", expectedVersion=0)) == [
        ws_session.rejected("INVALID_MOVE", "Jugada ilegal")
    ]
    assert world.published() == []


def test_non_participants_get_error_not_move_rejected():
    world = World()
    world.add()
    sent = frames(world, frame(type="move", uci="e2e4", expectedVersion=0), user=B)
    assert sent == [ws_session.error("GAME_NOT_FOUND", "La partida no existe o no es visible")]
    assert world.calls_to("/moves") == []


@pytest.mark.parametrize("failure", [httpx.ConnectError("caído"), httpx.ReadTimeout("lento")])
def test_game_logic_failures_are_error_not_move_rejected(failure):
    world = World()
    world.add()

    async def boom(request):
        if request.url.path.startswith("/internal/logic/"):
            raise failure
        return httpx.Response(204)

    world.handler = boom
    sent = frames(world, frame(type="move", uci="e2e4", expectedVersion=0))
    assert len(sent) == 1 and sent[0]["type"] == "error" and sent[0]["code"] == "SERVICES_UNAVAILABLE"


def test_unexpected_exceptions_become_internal_error(monkeypatch):
    world = World()
    world.add()

    async def boom(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(single_player, "handle_move", boom)
    sent = frames(world, frame(type="move", uci="e2e4", expectedVersion=0))
    assert sent == [ws_session.error("INTERNAL_ERROR", "Error interno del servidor")]


# ================================================================== rendición


def test_resign_frame_in_local_needs_the_side_and_in_bot_games_uses_the_human_color():
    world = World()
    world.add()
    sent = frames(world, frame(type="resign"))
    assert sent == [ws_session.rejected("VALIDATION_ERROR", 'side debe ser "white" o "black" en modo local')]
    assert frames(world, frame(type="resign", side="white")) == []
    assert world.body(world.calls_to("/resign")[0]) == {"side": "white"}
    assert world.published()[-1]["state"]["status"] == "finished"

    bot = World()
    vs_bot(bot, human="black", turn="black")
    frames(bot, frame(type="resign", side="white"))  # el side enviado se ignora
    assert bot.body(bot.calls_to("/resign")[0]) == {"side": "black"}


# ================================================================== turno del bot al conectar


def resume(world):
    async def scenario(ctx, send):
        await single_player.resume_bot_if_needed(ctx, world.games[GID])

    return run(world, scenario)


def test_resume_plays_the_bots_turn_when_it_is_pending():
    world = World()
    vs_bot(world, human="black", turn="white")
    resume(world)
    assert hub_types(world) == ["signal:bot_thinking", "state"]
    assert world.games[GID]["version"] == 1


def test_resume_does_nothing_when_it_is_the_humans_turn_or_the_game_is_local():
    for build in (lambda w: vs_bot(w, human="white", turn="white"), lambda w: w.add()):
        world = World()
        build(world)
        resume(world)
        assert world.calls == []


def test_resume_rereads_the_game_and_skips_a_turn_that_is_no_longer_the_bots():
    world = World()
    game = vs_bot(world, human="black", turn="white")
    stale = dict(game)
    world.games[GID].update(turn="black", version=1)  # mientras tanto jugó otro camino
    sent = []

    async def scenario(ctx, send):
        await single_player.resume_bot_if_needed(ctx, stale)

    run(world, scenario)
    assert world.calls_to("/best-move") == [] and world.published() == []


def test_resume_failure_warns_the_clients_with_the_real_code():
    world = World()
    vs_bot(world, human="black", turn="white")
    world.engine_error = (503, "ENGINE_BUSY")
    resume(world)
    assert world.published()[-1]["signal"]["code"] == "ENGINE_BUSY"
    assert world.games[GID]["version"] == 0


# ================================================================== orden y supervivencia


def test_frames_of_one_connection_are_processed_in_order():
    world = World()
    world.add()
    world.delay = 0.02

    async def scenario(ctx, send):
        queue, task = ws_session.start_frame_worker(ctx, A, GID, send)
        for version, uci in enumerate(["e2e4", "e7e5", "g1f3"]):
            queue.put_nowait(frame(type="move", uci=uci, expectedVersion=version))
        queue.put_nowait(None)
        await task

    sent = run(world, scenario)
    assert sent == []  # los tres se aceptaron: se procesaron en el orden recibido
    assert [world.body(c)["uci"] for c in world.calls_to("/moves")] == ["e2e4", "e7e5", "g1f3"]
    assert world.games[GID]["version"] == 3


def test_the_worker_is_registered_so_a_disconnect_does_not_cancel_it():
    world = World()
    world.add()
    world.delay = 0.05

    async def scenario(ctx, send):
        queue, task = ws_session.start_frame_worker(ctx, A, GID, send)
        assert len(ctx.tasks) == 1
        queue.put_nowait(frame(type="move", uci="e2e4", expectedVersion=0))
        queue.put_nowait(None)  # el cliente se fue: solo se cierra la cola
        await asyncio.sleep(0)  # y nada cancela al trabajador
        await ctx.tasks.drain(timeout=5)
        assert task.done() and not task.cancelled()

    run(world, scenario)
    assert world.games[GID]["version"] == 1 and len(world.published()) == 1


# ================================================================== proxy con un hub WebSocket real


class FakeHub:
    """Hub de Single Player falso (WebSocket real en un puerto local): envía un state al conectar y
    registra la cabecera X-User-Id y todo lo que el gateway le reenvíe."""

    def __init__(self):
        self.received: list[str] = []
        self.user_ids: list[str] = []
        self.connected = threading.Event()
        self.server = serve(self._handle, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.socket.getsockname()[1]}"

    def _handle(self, ws):
        self.user_ids.append(ws.request.headers.get("X-User-Id"))
        self.connected.set()
        ws.send(json.dumps({"type": "state", "state": {"version": 0}}))
        try:
            for message in ws:
                self.received.append(message)
        except Exception:  # noqa: BLE001
            pass

    def close(self):
        self.server.shutdown()


@pytest.fixture
def live(monkeypatch):
    world = World()
    hub = FakeHub()
    monkeypatch.setitem(main.UPSTREAMS, "single-player", hub.url)
    with TestClient(app) as client:
        app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(world.handler))
        client.cookies.set("session", token(A))
        yield client, world, hub
    hub.close()


def connect(client, game_id=GID):
    return client.websocket_connect(f"/ws/games/{game_id}", headers={"origin": "http://localhost"})


def wait_for(condition, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_the_hub_relays_its_messages_and_never_receives_the_clients_frames(live):
    client, world, hub = live
    world.add()
    with connect(client) as ws:
        assert ws.receive_json()["type"] == "state"  # el state inicial viene del hub
        ws.send_text(frame(type="move", uci="e2e4", expectedVersion=0))
        assert wait_for(lambda: world.calls_to("/moves"))  # lo opera el gateway en Game Logic
        ws.send_text("no es json")
        assert ws.receive_json() == ws_session.rejected("VALIDATION_ERROR", "El mensaje no es un JSON válido")
    assert hub.received == []  # el hub no recibe acciones
    assert hub.user_ids == [A]  # pero sí el usuario, para su sesión
    assert world.games[GID]["version"] == 1
    assert world.published()[0]["lastMove"] == "e2e4"


def test_errors_for_the_originating_client_go_straight_to_it(live):
    client, world, hub = live
    world.add(version=3)
    with connect(client) as ws:
        ws.receive_json()
        ws.send_text(frame(type="move", uci="e2e4", expectedVersion=1))
        assert ws.receive_json() == ws_session.rejected("VERSION_CONFLICT", "versión distinta")
        ws.send_text(frame(type="resign"))
        assert ws.receive_json()["code"] == "VALIDATION_ERROR"


def test_a_move_in_flight_still_completes_if_the_client_disconnects(live):
    client, world, hub = live
    world.add()
    world.delay = 0.3
    with connect(client) as ws:
        ws.receive_json()
        ws.send_text(frame(type="move", uci="e2e4", expectedVersion=0))
    # el cliente ya se fue; la jugada se aplica y se publica igual
    assert wait_for(lambda: world.published())
    assert world.games[GID]["version"] == 1 and world.published()[0]["lastMove"] == "e2e4"


def test_the_bots_pending_turn_is_resumed_when_a_client_connects(live):
    client, world, hub = live
    world.add(mode="vs_bot", participants=[{"userId": A, "color": "black"}], botLevel=5, turn="white")
    with connect(client) as ws:
        ws.receive_json()
        assert wait_for(lambda: world.games[GID]["version"] == 1)
    assert hub_types(world) == ["signal:bot_thinking", "state"]


def test_non_participants_are_closed_with_4404_before_touching_the_hub(live):
    client, world, hub = live
    world.add()
    client.cookies.set("session", token(B))
    with pytest.raises(WebSocketDisconnect) as e:
        with connect(client) as ws:
            ws.receive_text()
    assert e.value.code == 4404
    assert not hub.connected.is_set()


def test_unknown_game_is_closed_with_4404(live):
    client, world, hub = live
    with pytest.raises(WebSocketDisconnect) as e:
        with connect(client) as ws:
            ws.receive_text()
    assert e.value.code == 4404


def test_game_logic_down_at_connect_is_closed_with_1011(live):
    client, world, hub = live

    async def boom(request):
        raise httpx.ConnectError("caído")

    app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    with pytest.raises(WebSocketDisconnect) as e:
        with connect(client) as ws:
            ws.receive_text()
    assert e.value.code == 1011


def test_multiplayer_websocket_is_still_a_plain_proxy(live, monkeypatch):
    client, world, hub = live
    monkeypatch.setitem(main.UPSTREAMS, "multiplayer", hub.url)
    mid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    with client.websocket_connect(f"/ws/matches/{mid}", headers={"origin": "http://localhost"}) as ws:
        assert ws.receive_json()["type"] == "state"
        ws.send_text(frame(type="move", uci="e2e4"))
        assert wait_for(lambda: hub.received)
    assert hub.received == [frame(type="move", uci="e2e4")]  # multiplayer reenvía los frames tal cual
    assert world.calls == []
