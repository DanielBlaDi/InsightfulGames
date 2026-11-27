package chess.matches;

import java.util.List;

/** Response to a GET /internal/logic/games?userId=&limit=&cursor= request */
public record GamesPage(List<GameSummary> items, String nextCursor){}