package com.chess.gameservice.client;

import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.BestMove;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;

/**
 * Cliente de Botcito-juego: POST /internal/engine/best-move por el gateway interno (contrato, 14.4).
 * Los errores del catálogo (ENGINE_BUSY 503, ENGINE_TIMEOUT 504, SERVICES_UNAVAILABLE 503...)
 * pasan con su código real.
 */
@Component
public class BotcitoClient {

    private static final String NAME = "Botcito";

    public record BestMoveRequest(String fen, int botLevel) {
    }

    private final RestClient http;

    public BotcitoClient(@Value("${gateway.internal-url}") String gatewayUrl) {
        this.http = RestClients.create(gatewayUrl, Duration.ofSeconds(15));
    }

    public BestMove bestMove(String fen, int botLevel) {
        BestMove move = RestClients.exchange(NAME, http.post()
                .uri("/internal/engine/best-move")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new BestMoveRequest(fen, botLevel)), BestMove.class);

        if (move.uci() == null || move.uci().isBlank()) {
            throw ApiException.unavailable("Botcito devolvió una jugada vacía");
        }
        return move;
    }
}
