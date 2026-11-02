package chess.matches;

import java.util.List;

/** Response to a GET /internal/logic/games?userId=&limit=&cursor= request */
public record PagedMatches(List<GameSummary> matches, Integer cursor){}