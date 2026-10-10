package com.chess.gameservice.logic;

/**
 * @param legal   si la jugada era válida
 * @param fen     posición resultante (o la misma si la jugada fue ilegal)
 * @param turn    "WHITE" o "BLACK": a quién le toca después de la jugada
 * @param outcome estado de la partida tras la jugada
 * @param reason  si es ilegal: el motivo; si terminó: CHECKMATE, STALEMATE o DRAW_RULE
 */
public record MoveResult(boolean legal, String fen, String turn, Outcome outcome, String reason) {

    public enum Outcome { IN_PROGRESS, WHITE_WINS, BLACK_WINS, DRAW }

    public static MoveResult illegal(String fen, String turn, String reason) {
        return new MoveResult(false, fen, turn, Outcome.IN_PROGRESS, reason);
    }

    public boolean finished() {
        return legal && outcome != Outcome.IN_PROGRESS;
    }
}
