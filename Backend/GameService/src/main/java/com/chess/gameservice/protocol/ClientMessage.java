package com.chess.gameservice.protocol;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * Mensajes que envía el frontend:
 *  {"type":"create_game","mode":"LOCAL"|"BOT","difficulty":1-20,"color":"WHITE"|"BLACK","playerId":123}
 *  {"type":"move","move":"e2e4"}
 *  {"type":"resign"}
 * playerId es opcional: si el API Gateway envía el header X-User-Id, ese valor tiene prioridad.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ClientMessage(String type, String mode, Integer difficulty, String color, String move, Long playerId) {
}
