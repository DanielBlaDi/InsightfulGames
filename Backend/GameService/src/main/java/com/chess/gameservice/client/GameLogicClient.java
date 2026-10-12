package com.chess.gameservice.client;

import com.chess.gameservice.model.GameState;
import com.chess.gameservice.model.GameSummary;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.List;

/** Cliente REST de Game Logic (contrato, sección 3.5). */
@Component
public class GameLogicClient {

    private static final String NAME = "Game Logic";

    public record CreateBody(String userId, String mode, Integer botLevel, String playerColor) {
    }

    public record MoveBody(String uci) {
    }

    public record ResignBody(String side) {
    }

    private final RestClient http;

    public GameLogicClient(@Value("${gamelogic.url}") String baseUrl) {
        this.http = RestClients.create(baseUrl, Duration.ofSeconds(10));
    }

    public GameState createGame(String userId, String mode, Integer botLevel, String playerColor) {
        return RestClients.call(NAME, () -> http.post()
                .uri("/logic/games")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new CreateBody(userId, mode, botLevel, playerColor))
                .retrieve()
                .onStatus(status -> status.isError(), (req, res) -> {
                    throw RestClients.toApiException(NAME, res.getStatusCode().value(), res.getBody());
                })
                .body(GameState.class));
    }

    public GameState getGame(String gameId) {
        return RestClients.call(NAME, () -> http.get()
                .uri("/logic/games/{id}", gameId)
                .retrieve()
                .onStatus(status -> status.isError(), (req, res) -> {
                    throw RestClients.toApiException(NAME, res.getStatusCode().value(), res.getBody());
                })
                .body(GameState.class));
    }

    public List<GameSummary> listGames(String userId) {
        return RestClients.call(NAME, () -> http.get()
                .uri(uriBuilder -> uriBuilder.path("/logic/games").queryParam("userId", userId).build())
                .retrieve()
                .onStatus(status -> status.isError(), (req, res) -> {
                    throw RestClients.toApiException(NAME, res.getStatusCode().value(), res.getBody());
                })
                .body(new ParameterizedTypeReference<List<GameSummary>>() {
                }));
    }

    public GameState move(String gameId, String uci) {
        return RestClients.call(NAME, () -> http.post()
                .uri("/logic/games/{id}/moves", gameId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(new MoveBody(uci))
                .retrieve()
                .onStatus(status -> status.isError(), (req, res) -> {
                    throw RestClients.toApiException(NAME, res.getStatusCode().value(), res.getBody());
                })
                .body(GameState.class));
    }

    public GameState resign(String gameId, String side) {
        return RestClients.call(NAME, () -> http.post()
                .uri("/logic/games/{id}/resign", gameId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ResignBody(side))
                .retrieve()
                .onStatus(status -> status.isError(), (req, res) -> {
                    throw RestClients.toApiException(NAME, res.getStatusCode().value(), res.getBody());
                })
                .body(GameState.class));
    }
}
