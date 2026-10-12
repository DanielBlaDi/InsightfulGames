package com.chess.gameservice.client;

import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.BestMove;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;

/** Cliente de Botcito. Según el contrato (3.4) se llama a través del Gateway: POST /engine/best-move. */
@Component
public class BotcitoClient {

    private static final String NAME = "Botcito";

    public record BestMoveRequest(String fen, int level) {
    }

    private final RestClient http;

    public BotcitoClient(@Value("${gateway.internal-url}") String gatewayUrl) {
        this.http = RestClients.create(gatewayUrl, Duration.ofSeconds(15));
    }

    public BestMove bestMove(String fen, int level) {
        BestMove move = RestClients.call(NAME, () -> http.post()
                .uri("/engine/best-move")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new BestMoveRequest(fen, level))
                .retrieve()
                .onStatus(status -> status.isError(), (req, res) -> {
                    ApiException e = RestClients.toApiException(NAME, res.getStatusCode().value(), res.getBody());
                    // INVALID_FEN y NO_LEGAL_MOVES son errores de Botcito, no de quien llamó a este servicio
                    throw new ApiException(HttpStatus.BAD_GATEWAY, "BOT_UNAVAILABLE",
                            "Botcito no pudo calcular la jugada (" + e.code() + "): " + e.getMessage());
                })
                .body(BestMove.class));

        if (move == null || move.uci() == null || move.uci().isBlank()) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "BOT_UNAVAILABLE", "Botcito devolvió una respuesta vacía");
        }
        return move;
    }
}
