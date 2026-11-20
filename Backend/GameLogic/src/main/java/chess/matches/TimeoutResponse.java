package chess.matches;

public record TimeoutResponse(String gameId, String status, String result, String endReason, String finishedAt){}