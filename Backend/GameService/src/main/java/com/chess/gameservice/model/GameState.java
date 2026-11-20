package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;
import java.util.Map;

/**
 * GameState completo, tal como lo entrega Game Logic (contrato, 11.4.1). Single Player lo reenvía
 * sin quitar campos: el cliente necesita version para mandar expectedVersion en cada jugada.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GameState(
        String gameId,
        String mode,
        String visibility,
        String matchId,
        List<Participant> participants,
        Integer botLevel,
        TimeControl timeControl,
        Clocks clocks,
        String status,
        String turn,
        String fen,
        String initialFen,
        Map<String, List<String>> legalMoves,
        List<MoveEntry> moves,
        String drawOffer,
        Integer version,
        String result,
        String endReason,
        String createdAt,
        String finishedAt) {
}
