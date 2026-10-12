package com.chess.gameservice.protocol;

import com.fasterxml.jackson.annotation.JsonInclude;

/** Mensajes que envía el servidor. Los campos nulos no se serializan. */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ServerMessage(String type, String gameId, String mode, String fen, String turn,
                            String lastMove, String result, String reason, String message) {

    public static ServerMessage created(String gameId, String mode, String fen, String turn) {
        return new ServerMessage("game_created", gameId, mode, fen, turn, null, null, null, null);
    }

    public static ServerMessage state(String gameId, String fen, String turn, String lastMove) {
        return new ServerMessage("game_state", gameId, null, fen, turn, lastMove, null, null, null);
    }

    public static ServerMessage gameOver(String gameId, String result, String reason) {
        return new ServerMessage("game_over", gameId, null, null, null, null, result, reason, null);
    }

    public static ServerMessage error(String message) {
        return new ServerMessage("error", null, null, null, null, null, null, null, message);
    }
}
