package com.chess.gameservice.client;

import com.chess.gameservice.model.GameState;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;

/**
 * Cliente de Game Logic: solo lectura (GET /internal/logic/games/{id}), llamado directamente. Lo usan el
 * WebSocket (estado inicial) y el consumidor de game.finished; todo lo que cambia una partida lo hace el
 * gateway. No reenvía X-User-Id.
 */
@Component
public class GameLogicClient {

    private static final String NAME = "Game Logic";
    private static final String GAMES = "/internal/logic/games";

    private final RestClient http;

    public GameLogicClient(@Value("${services.game-logic-url}") String gameLogicUrl) {
        this.http = RestClients.create(gameLogicUrl, Duration.ofSeconds(10));
    }

    public GameState getGame(String gameId) {
        return RestClients.exchange(NAME, http.get().uri(GAMES + "/{id}", gameId), GameState.class);
    }
}
