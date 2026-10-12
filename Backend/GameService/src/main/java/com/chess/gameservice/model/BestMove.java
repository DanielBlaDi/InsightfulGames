package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Respuesta de POST /engine/best-move (sección 3.6). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record BestMove(String uci, String san, Evaluation evaluation) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Evaluation(String type, Integer value) {
    }
}
