package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * Cuerpo de POST /internal/single-player/games. botLevel y playerColor solo se usan en vs_bot.
 * timeControl es null o { minutes: 10 }; visibility es private por defecto.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record CreateGameRequest(String mode, Integer botLevel, String playerColor,
                                TimeControl timeControl, String visibility) {
}
