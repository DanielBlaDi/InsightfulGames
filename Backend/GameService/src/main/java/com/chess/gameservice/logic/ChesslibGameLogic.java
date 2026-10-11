package com.chess.gameservice.logic;

import com.chess.gameservice.logic.MoveResult.Outcome;
import com.github.bhlangonijr.chesslib.Board;
import com.github.bhlangonijr.chesslib.Piece;
import com.github.bhlangonijr.chesslib.PieceType;
import com.github.bhlangonijr.chesslib.Side;
import com.github.bhlangonijr.chesslib.Square;
import com.github.bhlangonijr.chesslib.move.Move;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.UUID;

/**
 * Implementación local con chesslib, solo para el perfil "mock"
 * (SPRING_PROFILES_ACTIVE=mock): permite probar el WebSocket sin Game Logic ni Mongo.
 * No guarda nada.
 */
@Component
@Profile("mock")
public class ChesslibGameLogic implements GameLogic {

    @Override
    public String createMatch(Long whitePlayerId, Long blackPlayerId) {
        return UUID.randomUUID().toString();
    }

    @Override
    public void finishMatch(String matchId, Outcome outcome, String reason) {
        // sin persistencia en el mock
    }

    @Override
    public MoveResult applyMove(String matchId, String fen, String uciMove, Long playerId) {
        Board board = new Board();
        board.loadFromFen(fen);

        Move move = parse(board, uciMove);
        if (move == null || !board.legalMoves().contains(move)) {
            return MoveResult.illegal(fen, turnOf(board), "Jugada ilegal: " + uciMove);
        }
        board.doMove(move);

        String turn = turnOf(board);
        if (board.isMated()) {
            // El que tiene el turno es quien quedó en jaque mate
            Outcome winner = turn.equals("BLACK") ? Outcome.WHITE_WINS : Outcome.BLACK_WINS;
            return new MoveResult(true, board.getFen(), turn, winner, "CHECKMATE");
        }
        if (board.isStaleMate()) {
            return new MoveResult(true, board.getFen(), turn, Outcome.DRAW, "STALEMATE");
        }
        if (board.isDraw()) {
            return new MoveResult(true, board.getFen(), turn, Outcome.DRAW, "DRAW_RULE");
        }
        return new MoveResult(true, board.getFen(), turn, Outcome.IN_PROGRESS, null);
    }

    private static String turnOf(Board board) {
        return board.getSideToMove() == Side.WHITE ? "WHITE" : "BLACK";
    }

    private static Move parse(Board board, String uci) {
        if (uci == null || (uci.length() != 4 && uci.length() != 5)) {
            return null;
        }
        try {
            Square from = Square.valueOf(uci.substring(0, 2).toUpperCase());
            Square to = Square.valueOf(uci.substring(2, 4).toUpperCase());
            if (uci.length() == 4) {
                return new Move(from, to);
            }
            PieceType type = switch (Character.toLowerCase(uci.charAt(4))) {
                case 'q' -> PieceType.QUEEN;
                case 'r' -> PieceType.ROOK;
                case 'b' -> PieceType.BISHOP;
                case 'n' -> PieceType.KNIGHT;
                default -> null;
            };
            return type == null ? null : new Move(from, to, Piece.make(board.getSideToMove(), type));
        } catch (IllegalArgumentException e) {
            return null;
        }
    }
}
