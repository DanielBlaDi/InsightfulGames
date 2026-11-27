package chess.matches;

public record ExpiredQueryResponse(String gameId, Integer version, String reason){}