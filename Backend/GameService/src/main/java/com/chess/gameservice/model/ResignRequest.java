package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Cuerpo de POST /games/{id}/resign: side solo se envía en modo local. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ResignRequest(String side) {
}
