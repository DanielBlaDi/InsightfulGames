package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Entrada de participants: en local hay dos con el mismo userId; en vs_bot, una sola (el humano). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record Participant(String userId, String color) {
}
