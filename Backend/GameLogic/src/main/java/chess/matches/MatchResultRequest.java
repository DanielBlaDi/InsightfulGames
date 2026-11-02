package chess.matches;

/** Cuerpo de POST /internal/logic/games/{id}/resign: { "side": "white" }. Es el bando que se rinde. */
public record MatchResultRequest(String side){}
