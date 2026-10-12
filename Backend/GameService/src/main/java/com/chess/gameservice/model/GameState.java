package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;
import java.util.Map;

/** Objeto GameState del contrato (sección 4). Lo arma Game Logic; este servicio solo lo reenvía. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GameState(
        String gameId,
        String userId,
        String mode,
        Integer botLevel,
        String playerColor,
        String status,
        String turn,
        String fen,
        Map<String, List<String>> legalMoves,
        List<MoveEntry> moves,
        String result,
        String endReason,
        String createdAt,
        String finishedAt) {
}
