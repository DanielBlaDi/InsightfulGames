package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** Configuración del reloj: null (sin reloj) o { minutes: 10 }. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record TimeControl(Integer minutes) {

    public static final int ALLOWED_MINUTES = 10;
}
