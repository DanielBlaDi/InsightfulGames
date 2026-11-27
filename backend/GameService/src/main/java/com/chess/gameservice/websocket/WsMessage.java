package com.chess.gameservice.websocket;

import com.chess.gameservice.model.GameState;
import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * Mensajes servidor -> cliente (contrato, 12.4.1). Cada tipo es un record propio para que la forma
 * sea exacta: game_over lleva siempre result (null en expired y account_deleted) y state conserva
 * los nulos del GameState anidado.
 */
public sealed interface WsMessage {

    String type();

    /** { type: "state", state, lastMove? }. lastMove se omite al conectar y cuando no hubo jugada. */
    record State(String type, GameState state,
                 @JsonInclude(JsonInclude.Include.NON_NULL) String lastMove) implements WsMessage {
    }

    /** { type: "move_rejected", code, message }: acción del cliente no aceptada. */
    record MoveRejected(String type, String code, String message) implements WsMessage {
    }

    /** { type: "bot_thinking" }. */
    record BotThinking(String type) implements WsMessage {
    }

    /** { type: "game_over", result, endReason }. Va justo después del state final. */
    record GameOver(String type, String result, String endReason) implements WsMessage {
    }

    /** { type: "error", code, message }: fallo ajeno a la jugada que no cambia la partida. */
    record ErrorMessage(String type, String code, String message) implements WsMessage {
    }

    static WsMessage state(GameState state, String lastMove) {
        return new State("state", state, lastMove);
    }

    static WsMessage moveRejected(String code, String message) {
        return new MoveRejected("move_rejected", code, message);
    }

    static WsMessage botThinking() {
        return new BotThinking("bot_thinking");
    }

    static WsMessage gameOver(String result, String endReason) {
        return new GameOver("game_over", result, endReason);
    }

    static WsMessage error(String code, String message) {
        return new ErrorMessage("error", code, message);
    }
}
