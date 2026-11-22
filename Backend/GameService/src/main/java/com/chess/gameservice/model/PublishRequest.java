package com.chess.gameservice.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * Cuerpo de POST /internal/single-player/games/{id}/publish. Lo envía el gateway tras operar en Game
 * Logic para que este hub avise a los clientes conectados por WebSocket. El hub no consulta a nadie.
 *
 * @param state    GameState vigente; se envía como { type: "state" } y, si terminó, game_over justo después
 * @param lastMove última jugada (uci), se omite si no hubo jugada
 * @param gameOver false para no enviar game_over aunque la partida haya terminado (p. ej. al cambiar la
 *                 visibilidad de una partida ya terminada); por omisión true
 * @param signal   aviso sin cambio de estado: bot_thinking o error
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PublishRequest(GameState state, String lastMove, Boolean gameOver, Signal signal) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Signal(String type, String code, String message) {
    }
}
