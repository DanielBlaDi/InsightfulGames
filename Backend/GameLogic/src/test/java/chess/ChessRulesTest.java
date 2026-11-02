package chess;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;

import chess.matches.ChessRules;
import chess.matches.ChessRules.Applied;

/** Pruebas de las reglas de ajedrez, sin Spring ni MongoDB. */
class ChessRulesTest{

    /** Juega una lista de jugadas UCI desde la posición dada y devuelve el resultado de la última. */
    private static Applied play(String initialFen, String... moves){
        List<String> previous = new ArrayList<>();
        Applied last = null;
        for(String move : moves){
            Optional<Applied> applied = ChessRules.apply(initialFen, previous, move);
            assertTrue(applied.isPresent(), "La jugada debía ser legal: " + move);
            last = applied.get();
            previous.add(move);
        }
        return last;
    }

    @Test
    void initialPositionHasExpectedLegalMoves(){
        var legal = ChessRules.legalMoves(ChessRules.START_FEN);

        assertEquals(List.of("e3", "e4"), legal.get("e2"));
        assertEquals(List.of("f3", "h3"), legal.get("g1"));
        assertFalse(legal.containsKey("e1"));
    }

    @Test
    void foolsMateIsCheckmateWonByBlack(){
        Applied last = play(ChessRules.START_FEN, "f2f3", "e7e5", "g2g4", "d8h4");

        assertEquals("Qh4#", last.san());
        assertEquals("white", last.turn());
        assertEquals("black", last.outcome().result());
        assertEquals("checkmate", last.outcome().endReason());
    }

    @Test
    void scholarsMateIsCheckmateWonByWhite(){
        Applied last = play(ChessRules.START_FEN, "e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7");

        assertEquals("Qxf7#", last.san());
        assertEquals("white", last.outcome().result());
        assertEquals("checkmate", last.outcome().endReason());
    }

    @Test
    void checkIsNotCheckmate(){
        Applied last = play(ChessRules.START_FEN, "e2e4", "f7f6", "d1h5");

        assertEquals("Qh5+", last.san());
        assertNull(last.outcome());
    }

    @Test
    void illegalAndMalformedMovesAreRejected(){
        assertTrue(ChessRules.apply(ChessRules.START_FEN, List.of(), "e2e5").isEmpty());
        assertTrue(ChessRules.apply(ChessRules.START_FEN, List.of(), "hola").isEmpty());
        assertTrue(ChessRules.apply(ChessRules.START_FEN, List.of(), "").isEmpty());
        assertTrue(ChessRules.apply(ChessRules.START_FEN, List.of(), null).isEmpty());
        //Es el turno de las blancas
        assertTrue(ChessRules.apply(ChessRules.START_FEN, List.of(), "e7e5").isEmpty());
    }

    @Test
    void stalemateIsADraw(){
        Applied last = play("k7/8/2K5/8/8/8/8/1Q6 w - - 0 1", "b1b6");

        assertEquals("draw", last.outcome().result());
        assertEquals("stalemate", last.outcome().endReason());
    }

    @Test
    void threefoldRepetitionIsADraw(){
        Applied last = play(ChessRules.START_FEN,
            "g1f3", "g8f6", "f3g1", "f6g8",
            "g1f3", "g8f6", "f3g1", "f6g8");

        assertEquals("draw", last.outcome().result());
        assertEquals("draw", last.outcome().endReason());
    }

    @Test
    void insufficientMaterialIsADraw(){
        //Rey y caballo contra rey: al coronar en caballo no queda material para dar mate
        Applied last = play("8/4P3/8/8/8/8/k6K/8 w - - 0 1", "e7e8n");

        assertEquals("draw", last.outcome().result());
    }

    @Test
    void promotionNeedsThePieceLetter(){
        String fen = "8/4P3/8/8/8/8/k6K/8 w - - 0 1";

        assertTrue(ChessRules.apply(fen, List.of(), "e7e8").isEmpty());
        Applied queen = play(fen, "e7e8q");
        assertEquals("e8=Q", queen.san());
        assertNull(queen.outcome());
    }

    @Test
    void castlingAndEnPassantAreSupported(){
        Applied castle = play("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1");
        assertEquals("O-O", castle.san());

        Applied enPassant = play("rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 3", "d4e3");
        assertEquals("dxe3", enPassant.san());
        assertNotNull(enPassant.fenAfter());
    }
}
