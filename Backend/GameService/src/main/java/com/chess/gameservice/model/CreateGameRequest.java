package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Cuerpo de POST /games: level y playerColor solo se usan en vs_bot. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CreateGameRequest(String mode, Integer level, String playerColor) {
}
