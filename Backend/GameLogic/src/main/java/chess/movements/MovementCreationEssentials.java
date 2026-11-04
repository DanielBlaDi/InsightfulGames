package chess.movements;

/**
 * Cuerpo de POST /internal/logic/games/{id}/moves: { "uci": "e2e4", "expectedVersion": 7 }.
 * Con promoción: "e7e8q". expectedVersion es obligatorio (contrato, 11.4.7).
 */
public record MovementCreationEssentials(String uci, Integer expectedVersion){}
