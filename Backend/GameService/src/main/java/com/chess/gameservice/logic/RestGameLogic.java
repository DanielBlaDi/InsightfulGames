package com.chess.gameservice.logic;

import com.chess.gameservice.logic.MoveResult.Outcome;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

import java.net.http.HttpClient;
import java.time.Duration;

/** Cliente REST del servicio Game Logic (tarea 6, Spring Boot + MongoDB). */
@Component
@Profile("!mock")
public class RestGameLogic implements GameLogic {

    public record CreateMatchRequest(Long whitePlayerId, Long blackPlayerId) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record MatchDto(String id) {}

    public record MoveRequest(String boardFenBeforeMove, String coordinateNotation, Long playerId) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record MoveResponse(String updatedFen, String matchStatus, String turn, String outcome, String reason) {}

    public record ResultRequest(String result, String reason) {}

    private final RestClient http;

    public RestGameLogic(@Value("${gamelogic.url}") String baseUrl) {
        // JdkClientHttpRequestFactory: SimpleClientHttpRequestFactory no soporta PATCH
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(client);
        factory.setReadTimeout(Duration.ofSeconds(10));
        this.http = RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
    }

    @Override
    public String createMatch(Long whitePlayerId, Long blackPlayerId) {
        MatchDto match = http.post()
                .uri("/matches")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new CreateMatchRequest(whitePlayerId, blackPlayerId))
                .retrieve()
                .body(MatchDto.class);
        if (match == null || match.id() == null) {
            throw new IllegalStateException("Game Logic no devolvió el ID de la partida");
        }
        return match.id();
    }

    @Override
    public MoveResult applyMove(String matchId, String fen, String uciMove, Long playerId) {
        try {
            MoveResponse r = http.patch()
                    .uri("/matches/{id}/movements", matchId)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new MoveRequest(fen, uciMove, playerId))
                    .retrieve()
                    .body(MoveResponse.class);
            if (r == null || r.updatedFen() == null) {
                throw new IllegalStateException("Respuesta vacía de Game Logic");
            }
            return new MoveResult(true, r.updatedFen(), r.turn(), Outcome.valueOf(r.outcome()), r.reason());
        } catch (HttpClientErrorException.BadRequest e) {
            // 400 = jugada ilegal (MovementNotValidAdvice en Game Logic)
            String turn = fen.split(" ")[1].equals("w") ? "WHITE" : "BLACK";
            return MoveResult.illegal(fen, turn, "Jugada ilegal: " + uciMove);
        }
    }

    @Override
    public void finishMatch(String matchId, Outcome outcome, String reason) {
        http.patch()
                .uri("/matches/{id}/result", matchId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ResultRequest(outcome.name(), reason))
                .retrieve()
                .toBodilessEntity();
    }
}
