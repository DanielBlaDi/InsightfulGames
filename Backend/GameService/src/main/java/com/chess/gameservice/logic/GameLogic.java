package com.chess.gameservice.logic;

import com.chess.gameservice.logic.MoveResult.Outcome;

/**
 * Contrato con el servicio Game Logic (tarea 6).
 * Implementaciones: RestGameLogic (por defecto, llama al servicio real)
 * y ChesslibGameLogic (perfil "mock", para probar sin Game Logic ni Mongo).
 */
public interface GameLogic {

    String START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

    /** Crea la partida (POST /matches) y devuelve su ID, que es el gameId que ve el cliente. */
    String createMatch(Long whitePlayerId, Long blackPlayerId);

    /**
     * Valida y guarda una jugada UCI ("e2e4", "e7e8q" en promoción) sobre la posición FEN.
     * Una jugada ilegal NO lanza excepción: devuelve MoveResult con legal=false.
     * Si el servicio no responde, lanza RuntimeException.
     */
    MoveResult applyMove(String matchId, String fen, String uciMove, Long playerId);

    /** Guarda el resultado final de la partida (mate, tablas o abandono). */
    void finishMatch(String matchId, Outcome outcome, String reason);
}
