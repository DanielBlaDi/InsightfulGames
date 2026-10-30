package chess;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.Map;

import com.github.bhlangonijr.chesslib.Board;
import com.github.bhlangonijr.chesslib.Side;
import com.github.bhlangonijr.chesslib.move.Move;
import com.github.bhlangonijr.chesslib.move.MoveList;

/**
 * Reglas de ajedrez. Clase sin Spring, para poder probarla sola.
 * Toda la posición se reconstruye desde el FEN inicial y las jugadas guardadas,
 * así que la repetición triple de posición sí se detecta.
 */
public final class ChessRules{
    public static final String START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

    /** result: "white" | "black" | "draw". endReason: "checkmate" | "stalemate" | "draw". */
    public record Outcome(String result, String endReason){}

    /** outcome es null si la partida continúa. */
    public record Applied(String san, String fenAfter, String turn, Outcome outcome){}

    private ChessRules(){}

    public static String colorOf(Side side){
        return side == Side.WHITE ? "white" : "black";
    }

    /** Casilla de origen -> casillas de destino legales (todo en minúsculas, ordenado). */
    public static Map<String, List<String>> legalMoves(String fen){
        Board board = new Board();
        board.loadFromFen(fen);

        Map<String, Set<String>> grouped = new TreeMap<>();
        for(Move move : board.legalMoves()){
            grouped.computeIfAbsent(move.getFrom().toString().toLowerCase(), k -> new LinkedHashSet<>())
                .add(move.getTo().toString().toLowerCase());
        }

        Map<String, List<String>> result = new TreeMap<>();
        for(Map.Entry<String, Set<String>> entry : grouped.entrySet()){
            List<String> destinations = new ArrayList<>(entry.getValue());
            destinations.sort(String::compareTo);
            result.put(entry.getKey(), destinations);
        }
        return result;
    }

    /**
     * Aplica una jugada UCI a la partida que empezó en initialFen y en la que ya se jugaron previousUci.
     * Devuelve null si la jugada es ilegal o está mal escrita.
     */
    public static Optional<Applied> apply(String initialFen, List<String> previousUci, String uci){
        Board board = replay(initialFen, previousUci);

        Optional<Move> found = findLegal(board, uci);
        if(found.isEmpty()){
            return Optional.empty();
        }
        Move move = found.get();

        MoveList sanList = new MoveList(board.getFen());
        sanList.add(move);
        String san = sanList.toSanArray()[0];

        board.doMove(move);

        Outcome outcome = null;
        if(board.isMated()){
            //Quien tiene el turno es quien quedó en jaque mate
            outcome = new Outcome(board.getSideToMove() == Side.WHITE ? "black" : "white", "checkmate");
        }else if(board.isStaleMate()){
            outcome = new Outcome("draw", "stalemate");
        }else if(board.isDraw()){
            //Material insuficiente, regla de 50 jugadas o repetición triple
            outcome = new Outcome("draw", "draw");
        }

        return Optional.of(new Applied(san, board.getFen(), colorOf(board.getSideToMove()), outcome));
    }

    private static Board replay(String initialFen, List<String> uciMoves){
        Board board = new Board();
        board.loadFromFen(initialFen);
        for(String uci : uciMoves){
            Move move = findLegal(board, uci)
                .orElseThrow(() -> new IllegalStateException("La partida guardada tiene una jugada ilegal: " + uci));
            board.doMove(move);
        }
        return board;
    }

    private static Optional<Move> findLegal(Board board, String uci){
        if(uci == null){
            return Optional.empty();
        }
        String wanted = uci.trim().toLowerCase();
        for(Move candidate : board.legalMoves()){
            if(candidate.toString().equals(wanted)){
                return Optional.of(candidate);
            }
        }
        return Optional.empty();
    }
}
