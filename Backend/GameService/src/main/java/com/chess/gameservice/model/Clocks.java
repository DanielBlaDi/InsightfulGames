package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * Estado del reloj: saldos en milisegundos al inicio del turno, turnStartedAt y deadline.
 * En vs_bot el saldo del bot es null, igual que turnStartedAt y deadline durante su turno.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record Clocks(Long white, Long black, String turnStartedAt, String deadline) {
}
