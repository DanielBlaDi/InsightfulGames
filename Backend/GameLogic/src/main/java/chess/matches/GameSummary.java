package chess.matches;

/**
 * Elemento de GET /internal/logic/games?userId=... Fechas en ISO 8601 UTC.
 * matchId solo en multiplayer; endReason null mientras no termina; color = el del usuario consultado
 * (null en partidas locales, donde juega con ambos colores).
 */
public record GameSummary(String gameId, String mode, String status, String result, String createdAt,
                          String matchId, String endReason, String color){
}
