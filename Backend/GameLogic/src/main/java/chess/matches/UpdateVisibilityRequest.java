package chess.matches;

/** Cuerpo de PATCH /internal/logic/games/{id}/visibility: { visibility, expectedVersion }. */
public record UpdateVisibilityRequest(String visibility, Integer expectedVersion){}
