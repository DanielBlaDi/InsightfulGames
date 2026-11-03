package com.chess.gameservice;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Gateway interno falso: atiende /internal/logic/* como un Game Logic mínimo (sin reglas de
 * ajedrez, pero con version, participants y expectedVersion) y /internal/engine/best-move como
 * Botcito-juego. Registra cada petición para comprobar rutas y cuerpos.
 */
final class FakeInternalGateway implements AutoCloseable {

    record Request(String method, String path, JsonNode body) {
    }

    private static final ObjectMapper MAPPER = new ObjectMapper();

    final List<Request> requests = new CopyOnWriteArrayList<>();
    final Map<String, ObjectNode> games = new ConcurrentHashMap<>();

    /** null: responde una jugada. Si no, código de error que devuelve Botcito (ENGINE_BUSY, ...). */
    volatile String engineError;
    /** true: Game Logic responde 500 a todo. */
    volatile boolean logicBroken;

    private final HttpServer server;

    FakeInternalGateway() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", this::handle);
        server.start();
    }

    String url() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    List<Request> requestsTo(String pathSuffix) {
        return requests.stream().filter(r -> r.path().endsWith(pathSuffix)).toList();
    }

    @Override
    public void close() {
        server.stop(0);
    }

    // ------------------------------------------------------------------

    private void handle(HttpExchange ex) throws IOException {
        String method = ex.getRequestMethod();
        String path = ex.getRequestURI().getPath();
        byte[] raw = ex.getRequestBody().readAllBytes();
        JsonNode body = raw.length == 0 ? null : MAPPER.readTree(raw);
        requests.add(new Request(method, path, body));

        // Un servicio no reenvía X-User-Id a otro (contrato, 4.4)
        if (ex.getRequestHeaders().containsKey("X-User-Id")) {
            error(ex, 400, "VALIDATION_ERROR", "X-User-Id no debe llegar a Game Logic ni a Botcito");
            return;
        }

        if (path.equals("/internal/engine/best-move") && method.equals("POST")) {
            engine(ex, body);
            return;
        }
        if (!path.startsWith("/internal/logic/games")) {
            error(ex, 404, "NOT_FOUND", "Ruta inexistente");
            return;
        }
        if (logicBroken) {
            error(ex, 500, "INTERNAL_ERROR", "fallo");
            return;
        }

        String[] parts = path.substring("/internal/logic/games".length()).split("/");
        // parts: ["", id, action?]
        if (parts.length <= 1) {
            if (method.equals("POST")) {
                create(ex, body);
            } else {
                error(ex, 404, "NOT_FOUND", "Ruta inexistente");
            }
            return;
        }
        ObjectNode game = games.get(parts[1]);
        if (game == null) {
            error(ex, 404, "GAME_NOT_FOUND", "La partida no existe");
            return;
        }
        String action = parts.length > 2 ? parts[2] : "";
        synchronized (game) {
            switch (method + " " + action) {
                case "GET " -> json(ex, 200, game);
                case "POST moves" -> move(ex, game, body);
                case "POST resign" -> {
                    finish(game, "white".equals(body.path("side").asText()) ? "black" : "white", "surrender");
                    json(ex, 200, game);
                }
                case "PATCH visibility" -> {
                    if (!versionMatches(ex, game, body)) {
                        return;
                    }
                    game.put("visibility", body.path("visibility").asText());
                    bump(game);
                    json(ex, 200, game);
                }
                default -> error(ex, 404, "NOT_FOUND", "Ruta inexistente");
            }
        }
    }

    private void create(HttpExchange ex, JsonNode body) throws IOException {
        String id = UUID.randomUUID().toString();
        ObjectNode game = MAPPER.createObjectNode();
        game.put("gameId", id);
        game.set("mode", body.get("mode"));
        game.set("visibility", body.get("visibility"));
        game.putNull("matchId");
        game.set("participants", body.get("participants"));
        game.set("botLevel", body.get("botLevel"));
        game.set("timeControl", body.get("timeControl"));
        if (body.get("timeControl").isNull()) {
            game.putNull("clocks");
        } else {
            ObjectNode clocks = game.putObject("clocks");
            clocks.put("white", 600000).put("black", 600000)
                    .put("turnStartedAt", "2026-10-29T15:00:00Z").put("deadline", "2026-10-29T15:10:00Z");
        }
        game.put("status", "in_progress");
        game.put("turn", "white");
        game.put("fen", "fen-0");
        game.put("initialFen", "fen-0");
        game.putObject("legalMoves").putArray("e2").add("e4");
        game.putArray("moves");
        game.putNull("drawOffer");
        game.put("version", 0);
        game.putNull("result");
        game.putNull("endReason");
        game.put("createdAt", "2026-10-29T15:00:00Z");
        game.putNull("finishedAt");
        games.put(id, game);
        json(ex, 201, game);
    }

    private void move(HttpExchange ex, ObjectNode game, JsonNode body) throws IOException {
        if (!versionMatches(ex, game, body)) {
            return;
        }
        String turn = game.get("turn").asText();
        ArrayNode moves = (ArrayNode) game.get("moves");
        String uci = body.get("uci").asText();
        ObjectNode entry = moves.addObject();
        entry.put("ply", moves.size()).put("color", turn).put("san", uci).put("uci", uci)
                .put("fenAfter", "fen-" + moves.size()).put("timestamp", "2026-10-29T15:00:05Z");
        game.put("turn", "white".equals(turn) ? "black" : "white");
        game.put("fen", "fen-" + moves.size());
        if (uci.equals("d8h4")) {
            finish(game, turn, "checkmate");
        } else {
            bump(game);
        }
        json(ex, 200, game);
    }

    private boolean versionMatches(HttpExchange ex, ObjectNode game, JsonNode body) throws IOException {
        if (body == null || !body.path("expectedVersion").isInt()) {
            error(ex, 400, "VALIDATION_ERROR", "Falta expectedVersion");
            return false;
        }
        if (body.get("expectedVersion").asInt() != game.get("version").asInt()) {
            error(ex, 409, "VERSION_CONFLICT", "La versión no coincide");
            return false;
        }
        return true;
    }

    void finish(ObjectNode game, String result, String endReason) {
        game.put("status", "finished");
        if (result == null) {
            game.putNull("result");
        } else {
            game.put("result", result);
        }
        game.put("endReason", endReason);
        game.putObject("legalMoves");
        game.put("finishedAt", "2026-10-29T15:20:00Z");
        bump(game);
    }

    private static void bump(ObjectNode game) {
        game.put("version", game.get("version").asInt() + 1);
    }

    private void engine(HttpExchange ex, JsonNode body) throws IOException {
        String failure = engineError;
        if (failure != null) {
            int status = failure.equals("ENGINE_TIMEOUT") ? 504 : 503;
            error(ex, status, failure, "Botcito: " + failure);
            return;
        }
        if (body == null || !body.path("botLevel").isInt() || !body.path("fen").isTextual()) {
            error(ex, 400, "VALIDATION_ERROR", "Se espera { fen, botLevel }");
            return;
        }
        ObjectNode move = MAPPER.createObjectNode();
        move.put("uci", "e7e5").put("san", "e5");
        move.putObject("evaluation").put("type", "cp").put("value", 0).put("perspective", "side_to_move");
        json(ex, 200, move);
    }

    private static void error(HttpExchange ex, int status, String code, String message) throws IOException {
        ObjectNode body = MAPPER.createObjectNode();
        body.putObject("error").put("code", code).put("message", message);
        json(ex, status, body);
    }

    private static void json(HttpExchange ex, int status, JsonNode body) throws IOException {
        byte[] out = MAPPER.writeValueAsString(body).getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().add("Content-Type", "application/json");
        ex.sendResponseHeaders(status, out.length);
        ex.getResponseBody().write(out);
        ex.close();
    }
}
