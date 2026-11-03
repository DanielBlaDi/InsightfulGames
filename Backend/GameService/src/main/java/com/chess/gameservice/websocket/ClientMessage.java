package com.chess.gameservice.websocket;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * Mensajes cliente -> servidor (contrato, 12.4.1):
 * { type: "move", uci, expectedVersion } y { type: "resign", side } (side solo en modo local).
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ClientMessage(String type, String uci, Integer expectedVersion, String side) {
}
