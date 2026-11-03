package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Cuerpo de PATCH /internal/single-player/games/{id}/visibility. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record VisibilityRequest(String visibility, Integer expectedVersion) {
}
