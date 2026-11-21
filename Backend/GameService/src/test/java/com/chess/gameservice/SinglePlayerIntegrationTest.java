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
import java.util.List;
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
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Single Player como hub (publish del gateway y WebSocket) contra un Game Logic
 * falso. Comprueba el aviso publish (orden, guarda de versión, señales), el estado inicial por WebSocket,
 * que el hub no opera por su cuenta, el cierre de no participantes y la notificación de game.finished.
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
        registry.add("services.game-logic-url", gateway::url);
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

    // ------------------------------------------------------------ publish (gateway -> hub)

    @Test
    void restOperationsMovedToTheGateway() throws Exception {
        String id = createLocal();
        assertEquals(404, request("POST", "/internal/single-player/games", USER, "{\"mode\":\"local\"}").status());
        for (String path : new String[]{"/internal/single-player/games/" + id, "/games", "/games/" + id}) {
            Response response = request("GET", path, USER, null);
            assertEquals(404, response.status(), path);
            assertEquals("NOT_FOUND", response.json().at("/error/code").asText());
        }
        assertEquals(404, request("POST", "/internal/single-player/games/" + id + "/resign", USER, "{\"side\":\"white\"}").status());
        assertEquals(404, request("PATCH", "/internal/single-player/games/" + id + "/visibility", USER,
                "{\"visibility\":\"shared\",\"expectedVersion\":0}").status());
        assertEquals(200, request("GET", "/health", null, null).status());
    }

    @Test
    void publishReachesConnectedClientsWithoutQueryingAnyService() throws Exception {
        String id = createLocal();
        try (Socket socket = connect(id, USER)) {
            socket.next(); // state inicial
            int before = gateway.requests.size();

            Response response = request("POST", publishPath(id), null,
                    publishBody(stateAt(id, 1, "in_progress", null, null), "e2e4", null));

            assertEquals(204, response.status());
            JsonNode moved = socket.next();
            assertEquals("state", moved.get("type").asText());
            assertEquals("e2e4", moved.get("lastMove").asText());
            assertEquals(1, moved.at("/state/version").asInt());
            assertEquals(before, gateway.requests.size(), "publish no debe llamar a Game Logic ni a Botcito");
        }
    }

    @Test
    void publishOfAFinishedGameSendsStateThenGameOver() throws Exception {
        String id = createLocal();
        try (Socket socket = connect(id, USER)) {
            socket.next();

            request("POST", publishPath(id), null,
                    publishBody(stateAt(id, 3, "finished", "black", "surrender"), null, null));

            assertEquals("finished", socket.next().at("/state/status").asText());
            JsonNode over = socket.next();
            assertEquals("game_over", over.get("type").asText());
            assertEquals("black", over.get("result").asText());
            assertEquals("surrender", over.get("endReason").asText());
        }
    }

    @Test
    void publishCanSkipGameOverWhenOnlyTheVisibilityChanged() throws Exception {
        String id = createLocal();
        try (Socket socket = connect(id, USER)) {
            socket.next();

            request("POST", publishPath(id), null,
                    publishBody(stateAt(id, 4, "finished", "black", "surrender"), null, false));

            assertEquals("state", socket.next().get("type").asText());
            assertNull(socket.messages.poll(300, TimeUnit.MILLISECONDS), "no debe llegar game_over");
        }
    }

    @Test
    void aStalePublishDoesNotMakeTheClientGoBack() throws Exception {
        String id = createLocal();
        try (Socket socket = connect(id, USER)) {
            socket.next();
            request("POST", publishPath(id), null, publishBody(stateAt(id, 5, "in_progress", null, null), "e2e4", null));
            assertEquals(5, socket.next().at("/state/version").asInt());

            Response stale = request("POST", publishPath(id), null,
                    publishBody(stateAt(id, 3, "in_progress", null, null), "d2d4", null));

            assertEquals(204, stale.status());
            assertNull(socket.messages.poll(300, TimeUnit.MILLISECONDS), "el aviso atrasado debe ignorarse");

            // Reenviar la misma version (resync) si se entrega
            request("POST", publishPath(id), null, publishBody(stateAt(id, 5, "in_progress", null, null), null, null));
            assertEquals(5, socket.next().at("/state/version").asInt());
        }
    }

    @Test
    void signalsReachClientsAsBotThinkingAndError() throws Exception {
        String id = createLocal();
        try (Socket socket = connect(id, USER)) {
            socket.next();

            request("POST", publishPath(id), null, "{\"signal\":{\"type\":\"bot_thinking\"}}");
            assertEquals("bot_thinking", socket.next().get("type").asText());

            request("POST", publishPath(id), null,
                    "{\"signal\":{\"type\":\"error\",\"code\":\"ENGINE_BUSY\",\"message\":\"Motores ocupados\"}}");
            JsonNode error = socket.next();
            assertEquals("error", error.get("type").asText());
            assertEquals("ENGINE_BUSY", error.get("code").asText());
        }
    }

    @Test
    void publishWithoutOpenSessionsIsANoOp() throws Exception {
        String id = createLocal();
        int before = gateway.requests.size();

        Response response = request("POST", publishPath(id), null,
                publishBody(stateAt(id, 1, "in_progress", null, null), "e2e4", null));

        assertEquals(204, response.status());
        assertEquals(before, gateway.requests.size());
    }

    @Test
    void invalidPublishRequestsAreValidationErrors() throws Exception {
        String id = createLocal();
        ObjectNode otherGame = stateAt(id, 1, "in_progress", null, null);
        otherGame.put("gameId", "otra-partida");
        ObjectNode noVersion = stateAt(id, 1, "in_progress", null, null);
        noVersion.remove("version");

        for (String body : new String[]{
                "{}",
                "no es json",
                publishBody(otherGame, null, null),
                publishBody(noVersion, null, null),
                "{\"signal\":{\"type\":\"desconocido\"}}",
                "{\"signal\":{\"type\":\"error\"}}"}) {
            Response response = request("POST", publishPath(id), null, body);
            assertEquals(400, response.status(), body);
            assertEquals("VALIDATION_ERROR", response.json().at("/error/code").asText());
        }
    }

    // ------------------------------------------------------------ WebSocket

    @Test
    void connectingSendsTheInitialStateAndTheHubDoesNotPlayForTheClient() throws Exception {
        String id = createLocal();
        try (Socket socket = connect(id, USER)) {
            JsonNode first = socket.next();
            assertEquals("state", first.get("type").asText());
            assertFalse(first.has("lastMove"));
            assertEquals(0, first.at("/state/version").asInt());
            assertEquals(2, first.at("/state/participants").size());
            int before = gateway.requests.size();

            // Las jugadas y la rendición las atiende el gateway: si un mensaje llega aquí, se ignora
            socket.send("{\"type\":\"move\",\"uci\":\"e2e4\",\"expectedVersion\":0}");
            socket.send("{\"type\":\"resign\",\"side\":\"white\"}");
            socket.send("no es json");

            assertNull(socket.messages.poll(400, TimeUnit.MILLISECONDS), "el hub no responde a los frames");
            assertEquals(before, gateway.requests.size(), "el hub no opera en Game Logic ni en Botcito");
            assertEquals("in_progress", gateway.games.get(id).get("status").asText());
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

    /** La partida se crea directamente en Game Logic (en produccion lo hace el gateway). */
    private String createInLogic(String mode, Integer botLevel, List<String[]> participants) throws Exception {
        ObjectNode body = mapper.createObjectNode();
        body.put("mode", mode).put("visibility", "private");
        body.putNull("timeControl");
        if (botLevel == null) {
            body.putNull("botLevel");
        } else {
            body.put("botLevel", botLevel);
        }
        ArrayNode list = body.putArray("participants");
        for (String[] p : participants) {
            list.addObject().put("userId", p[0]).put("color", p[1]);
        }
        HttpResponse<String> response = http.send(
                HttpRequest.newBuilder(URI.create(gateway.url() + "/internal/logic/games"))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(body.toString())).build(),
                HttpResponse.BodyHandlers.ofString());
        assertEquals(201, response.statusCode());
        return mapper.readTree(response.body()).get("gameId").asText();
    }

    private String createLocal() throws Exception {
        return createInLogic("local", null, List.of(new String[]{USER, "white"}, new String[]{USER, "black"}));
    }

    private static String publishPath(String gameId) {
        return "/internal/single-player/games/" + gameId + "/publish";
    }

    /** GameState de la partida (la del Game Logic falso) con la version y el estado indicados. */
    private ObjectNode stateAt(String gameId, int version, String status, String result, String endReason) {
        ObjectNode state = gateway.games.get(gameId).deepCopy();
        state.put("version", version);
        state.put("status", status);
        if (result == null) {
            state.putNull("result");
        } else {
            state.put("result", result);
        }
        if (endReason == null) {
            state.putNull("endReason");
        } else {
            state.put("endReason", endReason);
        }
        return state;
    }

    private String publishBody(ObjectNode state, String lastMove, Boolean gameOver) {
        ObjectNode body = mapper.createObjectNode();
        body.set("state", state);
        if (lastMove != null) {
            body.put("lastMove", lastMove);
        }
        if (gameOver != null) {
            body.put("gameOver", gameOver);
        }
        return body.toString();
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
