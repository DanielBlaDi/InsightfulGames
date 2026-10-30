package chess;

/** Elemento de GET /internal/logic/games?userId=... Fechas en ISO 8601 UTC. */
public record GameSummary(String gameId, String mode, String status, String result, String createdAt){
}
