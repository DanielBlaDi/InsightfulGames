package worker;

/** Elemento de GET /internal/logic/games/expired (contrato, 11.4): { gameId, version, reason }. */
public record ExpiredQueryResponse(String gameId, Integer version, String reason){}
