package com.chess.gameservice.websocket;

import com.chess.gameservice.model.GameState;
import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * Mensajes servidor -> cliente (contrato, sección 5). Los campos nulos no se serializan,
 * pero el GameState anidado conserva sus propios nulos (result: null, finishedAt: null...).
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record WsMessage(String type, GameState state, String lastMove, String code, String message,
                        String result, String endReason) {

    public static WsMessage state(GameState state, String lastMove) {
        return new WsMessage("state", state, lastMove, null, null, null, null);
    }

    public static WsMessage moveRejected(String code, String message) {
        return new WsMessage("move_rejected", null, null, code, message, null, null);
    }

    public static WsMessage botThinking() {
        return new WsMessage("bot_thinking", null, null, null, null, null, null);
    }

    public static WsMessage gameOver(String result, String endReason) {
        return new WsMessage("game_over", null, null, null, null, result, endReason);
    }

    /** Extensión al contrato: errores que no son una jugada rechazada (Botcito caído, etc.). */
    public static WsMessage error(String code, String message) {
        return new WsMessage("error", null, null, code, message, null, null);
    }
}
