package com.chess.gameservice.client;

import com.chess.gameservice.model.GameState;
import com.chess.gameservice.model.Participant;
import com.chess.gameservice.model.TimeControl;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.List;

/**
 * Cliente de Game Logic: /internal/logic/* por el gateway interno (contrato, 11.4 y 12.6).
 * No reenvía X-User-Id: es una llamada de servicio a servicio.
 */
@Component
public class GameLogicClient {

    private static final String NAME = "Game Logic";
    private static final String GAMES = "/internal/logic/games";

    /** Cuerpo de creación (11.4.5). Lo arma Single Player según el modo, nunca el cliente. */
    public record CreateBody(String mode, TimeControl timeControl, String visibility, Integer botLevel,
                             List<Participant> participants) {
    }

    public record MoveBody(String uci, int expectedVersion) {
    }

    public record ResignBody(String side) {
    }

    public record VisibilityBody(String visibility, int expectedVersion) {
    }

    private final RestClient http;

    public GameLogicClient(@Value("${gateway.internal-url}") String gatewayUrl) {
        this.http = RestClients.create(gatewayUrl, Duration.ofSeconds(10));
    }

    public GameState createGame(CreateBody body) {
        return RestClients.exchange(NAME, http.post()
                .uri(GAMES)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body), GameState.class);
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

    public GameState changeVisibility(String gameId, String visibility, int expectedVersion) {
        return RestClients.exchange(NAME, http.patch()
                .uri(GAMES + "/{id}/visibility", gameId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(new VisibilityBody(visibility, expectedVersion)), GameState.class);
    }
}
