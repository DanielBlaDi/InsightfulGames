package worker;

public record ExpiredQueryResponse(String gameId, Integer version, String reason){}