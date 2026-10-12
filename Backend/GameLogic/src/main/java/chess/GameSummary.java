package chess;

/** Elemento de GET /logic/games?userId=... (contrato, sección 3.4). Fechas en ISO 8601 UTC. */
public record GameSummary(String gameId, String mode, String status, String result, String createdAt){
}
