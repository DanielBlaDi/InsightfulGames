package chess.matches;

/**
 * Elemento de GET /internal/logic/games?userId=... (contrato, 11.4.1). color es el del usuario que
 * pide la lista; null en local. Fechas en ISO 8601 UTC.
 */
public record GameSummary(String gameId, String mode, String matchId, String status, String result, String endReason, String color, String createdAt){
}
