package com.chess.gameservice.model;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import com.chess.gameservice.websocket.WsMessage;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/** El GameState del contrato (11.4.1) pasa por Single Player sin perder ni cambiar campos. */
class GameStateContractTest {

    static final String CONTRACT_STATE = """
            {
              "gameId": "3f2b1c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
              "mode": "vs_bot",
              "visibility": "private",
              "matchId": null,
              "participants": [ { "userId": "7d1f9d5e-3c2b-4f0e-9a41-0b5f6d7a8c90", "color": "white" } ],
              "botLevel": 5,
              "timeControl": { "minutes": 10 },
              "clocks": { "white": 600000, "black": null, "turnStartedAt": "2026-10-29T15:00:00Z", "deadline": "2026-10-29T15:10:00Z" },
              "status": "in_progress",
              "turn": "white",
              "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
              "initialFen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
              "legalMoves": { "e2": ["e3", "e4"] },
              "moves": [ { "ply": 1, "color": "white", "san": "e4", "uci": "e2e4", "fenAfter": "x", "timestamp": "2026-10-29T15:00:05Z" } ],
              "drawOffer": null,
              "version": 7,
              "result": null,
              "endReason": null,
              "createdAt": "2026-10-29T15:00:00Z",
              "finishedAt": null
            }""";

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void gameStateRoundTripsWithoutLosingFields() throws Exception {
        JsonNode original = mapper.readTree(CONTRACT_STATE);
        GameState state = mapper.readValue(CONTRACT_STATE, GameState.class);

        assertEquals(original, reparse(state));
        assertEquals(7, state.version());
    }

    @Test
    void stateMessageCarriesTheFullGameState() throws Exception {
        GameState state = mapper.readValue(CONTRACT_STATE, GameState.class);

        JsonNode message = reparse(WsMessage.state(state, "e2e4"));
        assertEquals("state", message.get("type").asText());
        assertEquals("e2e4", message.get("lastMove").asText());
        assertEquals(mapper.readTree(CONTRACT_STATE), message.get("state"));

        JsonNode onConnect = mapper.valueToTree(WsMessage.state(state, null));
        assertEquals(false, onConnect.has("lastMove"));
    }

    /** Serializa y vuelve a leer, para comparar JSON sin depender del tipo numérico de cada nodo. */
    private JsonNode reparse(Object value) throws Exception {
        return mapper.readTree(mapper.writeValueAsString(value));
    }

    @Test
    void serverMessagesHaveTheContractShape() throws Exception {
        assertEquals(mapper.readTree("{\"type\":\"game_over\",\"result\":null,\"endReason\":\"expired\"}"),
                mapper.valueToTree(WsMessage.gameOver(null, "expired")));
        assertEquals(mapper.readTree("{\"type\":\"bot_thinking\"}"), mapper.valueToTree(WsMessage.botThinking()));
        assertEquals(mapper.readTree("{\"type\":\"move_rejected\",\"code\":\"INVALID_MOVE\",\"message\":\"m\"}"),
                mapper.valueToTree(WsMessage.moveRejected("INVALID_MOVE", "m")));
        assertEquals(mapper.readTree("{\"type\":\"error\",\"code\":\"ENGINE_BUSY\",\"message\":\"m\"}"),
                mapper.valueToTree(WsMessage.error("ENGINE_BUSY", "m")));
    }
}
