package chess;

import java.util.List;
import java.util.Map;

/**
 * Objeto GameState del contrato (sección 4): lo que Game Logic responde en crear, consultar,
 * mover y rendirse. Las fechas van como texto ISO 8601 UTC.
 */
public record GameState(
    String gameId,
    String userId,
    String mode,
    Integer botLevel,
    String playerColor,
    String status,
    String turn,
    String fen,
    Map<String, List<String>> legalMoves,
    List<MoveEntry> moves,
    String result,
    String endReason,
    String createdAt,
    String finishedAt
){
    /** Una jugada dentro de "moves". */
    public record MoveEntry(int ply, String san, String uci, String fenAfter, String timestamp){
    }
}
