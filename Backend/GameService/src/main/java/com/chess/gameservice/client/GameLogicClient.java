package com.chess.gameservice.client;

import com.chess.gameservice.model.GameState;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;

/**
 * Cliente de Game Logic: /internal/logic/*, llamado directamente (contrato, 11.4 y 12.6). Lo usan el WebSocket
 * y el consumidor de game.finished; las operaciones REST las hace el gateway. No reenvía X-User-Id.
 */
@Component
public class GameLogicClient {

    private static final String NAME = "Game Logic";
    private static final String GAMES = "/internal/logic/games";

    public record MoveBody(String uci, int expectedVersion) {
    }

    public record ResignBody(String side) {
    }

    private final RestClient http;

    public GameLogicClient(@Value("${services.game-logic-url}") String gameLogicUrl) {
        this.http = RestClients.create(gameLogicUrl, Duration.ofSeconds(10));
    }

    public GameState getGame(String gameId) {
        return RestClients.exchange(NAME, http.get().uri(GAMES + "/{id}", gameId), GameState.class);
    }

    public GameState move(String gameId, String uci, int expectedVersion) {
        return RestClients.exchange(NAME, http.post()
                .uri(GAMES + "/{id}/moves", gameId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(new MoveBody(uci, expectedVersion)), GameState.class);
    }

    public GameState resign(String gameId, String side) {
        return RestClients.exchange(NAME, http.post()
                .uri(GAMES + "/{id}/resign", gameId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ResignBody(side)), GameState.class);
    }
}
