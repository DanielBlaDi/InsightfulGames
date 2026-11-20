package com.chess.gameservice;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import com.chess.gameservice.events.GameFinishedListener;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Single Player real (REST y WebSocket) contra un gateway interno falso que hace de Game Logic y
 * Botcito-juego. Comprueba rutas internas, cuerpo de creación, GameState completo, expectedVersion,
 * participantes, visibilidad, códigos de error y la notificación de game.finished.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SinglePlayerIntegrationTest {

    static final String USER = "7d1f9d5e-3c2b-4f0e-9a41-0b5f6d7a8c90";
    static final String OTHER = "11111111-2222-4333-8444-555555555555";

    static final FakeInternalGateway gateway;

    static {
        try {
            gateway = new FakeInternalGateway();
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("gateway.internal-url", gateway::url);
        // Sin broker en la prueba: el consumidor se invoca directamente.
        registry.add("spring.rabbitmq.listener.simple.auto-startup", () -> "false");
    }

    @AfterAll
    static void stopGateway() {
        gateway.close();
    }

    @LocalServerPort
    int port;

    @Autowired
    GameFinishedListener listener;

    final ObjectMapper mapper = new ObjectMapper();
    final HttpClient http = HttpClient.newHttpClient();

    @BeforeEach
    void reset() {
        gateway.requests.clear();
        gateway.engineError = null;
        gateway.logicBroken = false;
    }

    // ------------------------------------------------------------ REST

    @Test
    void localGameIsCreatedInGameLogicWithTheContractBody() throws Exception {
        Response created = request("POST", "/internal/single-player/games", USER, "{\"mode\":\"local\"}");

        assertEquals(201, created.status());
        JsonNode body = gateway.requestsTo("/internal/logic/games").get(0).body();
        assertEquals("local", body.get("mode").asText());
        assertEquals("private", body.get("visibility").asText());
        assertTrue(body.get("timeControl").isNull());
        assertTrue(body.get("botLevel").isNull());
        assertEquals(2, body.get("participants").size());
        assertEquals(USER, body.at("/participants/0/userId").asText());
        assertEquals("white", body.at("/participants/0/color").asText());
        assertEquals(USER, body.at("/participants/1/userId").asText());
        assertEquals("black", body.at("/participants/1/color").asText());
        assertFalse(body.has("userId"));
        assertFalse(body.has("playerColor"));

        // GameState completo, sin campos descartados
        JsonNode state = created.json();
        for (String field : new String[]{"gameId", "mode", "visibility", "matchId", "participants", "botLevel",
                "timeControl", "clocks", "status", "turn", "fen", "initialFen", "legalMoves", "moves",
                "drawOffer", "version", "result", "endReason", "createdAt", "finishedAt"}) {
            assertTrue(state.has(field), "falta " + field);
        }
        assertEquals(0, state.get("version").asInt());
    }

    @Test
    void botGameAsBlackOpensWithTheInternalEngineRoute() throws Exception {
        Response created = request("POST", "/internal/single-player/games", USER,
                "{\"mode\":\"vs_bot\",\"botLevel\":7,\"playerColor\":\"black\",\"timeControl\":{\"minutes\":10},\"visibility\":\"shared\"}");

        assertEquals(201, created.status());
        JsonNode create = gateway.requestsTo("/internal/logic/games").get(0).body();
        assertEquals(1, create.get("participants").size());
        assertEquals("black", create.at("/participants/0/color").asText());
        assertEquals(7, create.get("botLevel").asInt());
        assertEquals(10, create.at("/timeControl/minutes").asInt());
        assertEquals("shared", create.get("visibility").asText());

        JsonNode engine = gateway.requestsTo("/internal/engine/best-move").get(0).body();
        assertEquals(7, engine.get("botLevel").asInt());
        assertEquals("fen-0", engine.get("fen").asText());
        assertFalse(engine.has("level"));

        JsonNode botMove = gateway.requestsTo("/moves").get(0).body();
        assertEquals(0, botMove.get("expectedVersion").asInt());
        assertEquals(1, created.json().get("version").asInt());
        assertEquals("white", created.json().at("/moves/0/color").asText());
    }

    @Test
    void invalidCreationRequestsAreValidationErrors() throws Exception {
        for (String body : new String[]{
                "{\"mode\":\"vs_bot\",\"level\":5,\"playerColor\":\"white\"}",
                "{\"mode\":\"local\",\"timeControl\":{\"minutes\":5}}",
                "{\"mode\":\"local\",\"visibility\":\"public\"}",
                "no es json"}) {
            Response response = request("POST", "/internal/single-player/games", USER, body);
            assertEquals(400, response.status(), body);
            assertEquals("VALIDATION_ERROR", response.json().at("/error/code").asText());
        }
        assertTrue(gateway.requests.isEmpty());
    }

    @Test
    void readingRequiresParticipantOrSharedGame() throws Exception {
        String id = createLocal();

        assertEquals(200, request("GET", "/internal/single-player/games/" + id, USER, null).status());

        Response other = request("GET", "/internal/single-player/games/" + id, OTHER, null);
        assertEquals(404, other.status());
        assertEquals("GAME_NOT_FOUND", other.json().at("/error/code").asText());

        Response noUser = request("GET", "/internal/single-player/games/" + id, null, null);
        assertEquals(401, noUser.status());
        assertEquals("UNAUTHORIZED", noUser.json().at("/error/code").asText());

        int version = request("GET", "/internal/single-player/games/" + id, USER, null).json().get("version").asInt();
        request("PATCH", "/internal/single-player/games/" + id + "/visibility", USER,
                "{\"visibility\":\"shared\",\"expectedVersion\":" + version + "}");
        assertEquals(200, request("GET", "/internal/single-player/games/" + id, OTHER, null).status());
    }

    @Test
    void visibilityForwardsExpectedVersionAndReportsConflicts() throws Exception {
        String id = createLocal();

        Response changed = request("PATCH", "/internal/single-player/games/" + id + "/visibility", USER,
                "{\"visibility\":\"shared\",\"expectedVersion\":0}");
        assertEquals(200, changed.status());
        assertEquals("shared", changed.json().get("visibility").asText());
        assertEquals(1, changed.json().get("version").asInt());

        Response stale = request("PATCH", "/internal/single-player/games/" + id + "/visibility", USER,
                "{\"visibility\":\"private\",\"expectedVersion\":0}");
        assertEquals(409, stale.status());
        assertEquals("VERSION_CONFLICT", stale.json().at("/error/code").asText());

        Response notParticipant = request("PATCH", "/internal/single-player/games/" + id + "/visibility", OTHER,
                "{\"visibility\":\"private\",\"expectedVersion\":1}");
        assertEquals(404, notParticipant.status());
    }

    @Test
    void resignOverRestUsesTheGivenSideInLocal() throws Exception {
        String id = createLocal();

        Response resigned = request("POST", "/internal/single-player/games/" + id + "/resign", USER,
                "{\"side\":\"white\"}");

        assertEquals(200, resigned.status());
        assertEquals("black", resigned.json().get("result").asText());
        assertEquals("surrender", resigned.json().get("endReason").asText());
        assertEquals("white", gateway.requestsTo("/resign").get(0).body().get("side").asText());
    }

    @Test
    void failingDependencyIsServicesUnavailable503() throws Exception {
        String id = createLocal();
        gateway.logicBroken = true;

        Response response = request("GET", "/internal/single-player/games/" + id, USER, null);

        assertEquals(503, response.status());
        assertEquals("SERVICES_UNAVAILABLE", response.json().at("/error/code").asText());
    }

    @Test
    void legacyRoutesWereRetired() throws Exception {
        String id = createLocal();
        for (String path : new String[]{"/games", "/games/" + id}) {
            Response response = request("GET", path, USER, null);
            assertEquals(404, response.status(), path);
            assertEquals("NOT_FOUND", response.json().at("/error/code").asText());
        }
        assertEquals(404, request("POST", "/games", USER, "{\"mode\":\"local\"}").status());
        assertEquals(200, request("GET", "/health", null, null).status());
    }

    // ------------------------------------------------------------ WebSocket

    @Test
    void localGameIsPlayedOverWebSocketWithExpectedVersion() throws Exception {
        String id = createLocal();
        try (Socket socket = connect(id, USER)) {
            JsonNode first = socket.next();
            assertEquals("state", first.get("type").asText());
            assertFalse(first.has("lastMove"));
            assertEquals(0, first.at("/state/version").asInt());
            assertEquals(2, first.at("/state/participants").size());

            socket.send("{\"type\":\"move\",\"uci\":\"e2e4\",\"expectedVersion\":0}");
            JsonNode moved = socket.next();
            assertEquals("state", moved.get("type").asText());
            assertEquals("e2e4", moved.get("lastMove").asText());
            assertEquals(1, moved.at("/state/version").asInt());
            assertEquals("white", moved.at("/state/moves/0/color").asText());

            JsonNode forwarded = gateway.requestsTo("/moves").get(0).body();
            assertEquals("e2e4", forwarded.get("uci").asText());
            assertEquals(0, forwarded.get("expectedVersion").asInt());

            // Misma versión otra vez: llega el state vigente y luego move_rejected
            socket.send("{\"type\":\"move\",\"uci\":\"e7e5\",\"expectedVersion\":0}");
            JsonNode resynced = socket.next();
            assertEquals("state", resynced.get("type").asText());
            assertEquals(1, resynced.at("/state/version").asInt());
            JsonNode rejected = socket.next();
            assertEquals("move_rejected", rejected.get("type").asText());
            assertEquals("VERSION_CONFLICT", rejected.get("code").asText());

            socket.send("{\"type\":\"move\",\"uci\":\"e7e5\"}");
            JsonNode missing = socket.next();
            assertEquals("move_rejected", missing.get("type").asText());
            assertEquals("VALIDATION_ERROR", missing.get("code").asText());
        }
    }

    @Test
    void mateSendsStateThenGameOver() throws Exception {
        String id = createLocal();
        try (Socket socket = connect(id, USER)) {
            socket.next();
            socket.send("{\"type\":\"move\",\"uci\":\"d8h4\",\"expectedVersion\":0}");
            JsonNode state = socket.next();
            assertEquals("finished", state.at("/state/status").asText());
            JsonNode over = socket.next();
            assertEquals("game_over", over.get("type").asText());
            assertEquals("white", over.get("result").asText());
            assertEquals("checkmate", over.get("endReason").asText());
        }
    }

    @Test
    void botErrorsArriveWithTheirRealCodeAndTheHumanMoveIsKept() throws Exception {
        String id = request("POST", "/internal/single-player/games", USER,
                "{\"mode\":\"vs_bot\",\"botLevel\":3,\"playerColor\":\"white\"}").json().get("gameId").asText();
        gateway.engineError = "ENGINE_BUSY";

        try (Socket socket = connect(id, USER)) {
            socket.next();
            socket.send("{\"type\":\"move\",\"uci\":\"e2e4\",\"expectedVersion\":0}");
            assertEquals("state", socket.next().get("type").asText());
            assertEquals("bot_thinking", socket.next().get("type").asText());
            JsonNode error = socket.next();
            assertEquals("error", error.get("type").asText());
            assertEquals("ENGINE_BUSY", error.get("code").asText());

            // Es turno del bot: el humano no puede mover
            socket.send("{\"type\":\"move\",\"uci\":\"d2d4\",\"expectedVersion\":1}");
            JsonNode rejected = socket.next();
            assertEquals("move_rejected", rejected.get("type").asText());
            assertEquals("NOT_YOUR_TURN", rejected.get("code").asText());
        }

        // Al reconectar con Botcito disponible se retoma el turno del bot
        gateway.engineError = null;
        try (Socket socket = connect(id, USER)) {
            assertEquals(1, socket.next().at("/state/version").asInt());
            assertEquals("bot_thinking", socket.next().get("type").asText());
            JsonNode afterBot = socket.next();
            assertEquals("e7e5", afterBot.get("lastMove").asText());
            assertEquals(2, afterBot.at("/state/version").asInt());
        }
    }

    @Test
    void nonParticipantsAreClosedWith4404() throws Exception {
        String id = createLocal();
        try (Socket socket = connect(id, OTHER)) {
            assertEquals(4404, socket.closed.get(5, TimeUnit.SECONDS).getCode());
        }
    }

    // ------------------------------------------------------------ game.finished

    @Test
    void gameFinishedEventNotifiesOpenSessions() throws Exception {
        String id = createLocal();
        try (Socket socket = connect(id, USER)) {
            socket.next();
            gateway.finish(gateway.games.get(id), null, "account_deleted");

            listener.onGameFinished(event(id, "local"));

            JsonNode state = socket.next();
            assertEquals("state", state.get("type").asText());
            assertEquals("finished", state.at("/state/status").asText());
            JsonNode over = socket.next();
            assertEquals("game_over", over.get("type").asText());
            assertTrue(over.has("result"), "game_over lleva result aunque sea null");
            assertTrue(over.get("result").isNull());
            assertEquals("account_deleted", over.get("endReason").asText());

            // Un evento multiplayer no le corresponde
            listener.onGameFinished(event(id, "multiplayer"));
            assertNull(socket.messages.poll(300, TimeUnit.MILLISECONDS));
        }
    }

    // ------------------------------------------------------------ utilidades

    record Response(int status, String body, ObjectMapper mapper) {
        JsonNode json() throws IOException {
            return mapper.readTree(body);
        }
    }

    private String createLocal() throws Exception {
        Response created = request("POST", "/internal/single-player/games", USER, "{\"mode\":\"local\"}");
        assertEquals(201, created.status());
        return created.json().get("gameId").asText();
    }

    private Response request(String method, String path, String userId, String body) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create("http://localhost:" + port + path))
                .method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                        : HttpRequest.BodyPublishers.ofString(body))
                .header("Content-Type", "application/json");
        if (userId != null) {
            builder.header("X-User-Id", userId);
        }
        HttpResponse<String> response = http.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        return new Response(response.statusCode(), response.body(), mapper);
    }

    private static Message event(String gameId, String mode) {
        String json = "{\"eventType\":\"game.finished\",\"gameId\":\"" + gameId + "\",\"mode\":\"" + mode
                + "\",\"participants\":[],\"result\":null,\"endReason\":\"account_deleted\"}";
        return new Message(json.getBytes(StandardCharsets.UTF_8), new MessageProperties());
    }

    private Socket connect(String gameId, String userId) throws Exception {
        Socket socket = new Socket();
        WebSocketHttpHeaders headers = new WebSocketHttpHeaders();
        headers.add("X-User-Id", userId);
        socket.session = new StandardWebSocketClient()
                .execute(socket, headers, URI.create("ws://localhost:" + port + "/internal/single-player/ws/games/" + gameId))
                .get(5, TimeUnit.SECONDS);
        return socket;
    }

    final class Socket extends TextWebSocketHandler implements AutoCloseable {
        final BlockingQueue<String> messages = new LinkedBlockingQueue<>();
        final CompletableFuture<CloseStatus> closed = new CompletableFuture<>();
        WebSocketSession session;

        @Override
        protected void handleTextMessage(WebSocketSession session, TextMessage message) {
            messages.add(message.getPayload());
        }

        @Override
        public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
            closed.complete(status);
        }

        JsonNode next() throws Exception {
            String payload = messages.poll(5, TimeUnit.SECONDS);
            assertNotNull(payload, "no llegó ningún mensaje");
            return mapper.readTree(payload);
        }

        void send(String json) throws IOException {
            session.sendMessage(new TextMessage(json));
        }

        @Override
        public void close() throws IOException {
            if (session.isOpen()) {
                session.close();
            }
        }
    }
}
