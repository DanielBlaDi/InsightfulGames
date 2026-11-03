package chess.matches;

/** Cuerpo de POST /internal/logic/games/{id}/resign, /internal/logic/games/{id}/abandon, y /internal/logic/games/{id}/draw/* : { "side": "white" }. Es el bando que se rinde, que ofreció empate o responde a este. */
public record MatchResultRequest(String side){}
