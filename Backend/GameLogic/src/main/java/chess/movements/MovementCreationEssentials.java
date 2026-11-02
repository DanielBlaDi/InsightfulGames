package chess.movements;

/** Cuerpo de POST /internal/logic/games/{id}/moves: { "uci": "e2e4" }. Con promoción: "e7e8q". */
public record MovementCreationEssentials(String uci){}
