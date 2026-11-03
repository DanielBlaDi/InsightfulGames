package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Respuesta de POST /internal/engine/best-move (contrato, 14.4). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record BestMove(String uci, String san, Evaluation evaluation) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Evaluation(String type, Integer value, String perspective) {
    }
}
