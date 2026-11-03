package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Una jugada de moves. color es el bando que tenía el turno antes de la jugada. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record MoveEntry(int ply, String color, String san, String uci, String fenAfter, String timestamp) {
}
