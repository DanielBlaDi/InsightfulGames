package chess.matches;

import java.util.List;
import java.util.Map;

/**
 * Lo que Game Logic responde en crear, consultar,
 * mover y rendirse. Las fechas van como texto ISO 8601 UTC.
 */
public record GameState(
    String gameId,
    String mode,
    String visibility,
    String matchId,
    List<Participant> participants,
    Integer botLevel,
    TimeControl timeControl,
    Clocks clocks,
    String status,
    String turn,
    String fen,
    String initialFen,
    Map<String, List<String>> legalMoves,
    List<MoveEntry> moves,
    String drawOffer,
    int version,
    String result,
    String endReason,
    String createdAt,
    String finishedAt
){
    /** Una jugada dentro de "moves" */
    public record MoveEntry(int ply, String san, String uci, String fenAfter, String timestamp){
    }
}
