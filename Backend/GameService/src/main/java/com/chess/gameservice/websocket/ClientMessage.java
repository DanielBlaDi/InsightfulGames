package com.chess.gameservice.websocket;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * Mensajes cliente -> servidor (contrato, sección 5):
 * {"type":"move","uci":"e2e4"} y {"type":"resign","side":"white"} (side solo en modo local).
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ClientMessage(String type, String uci, String side) {
}
