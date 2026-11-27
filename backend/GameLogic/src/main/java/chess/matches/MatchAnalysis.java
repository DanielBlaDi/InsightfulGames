package chess.matches;

import java.util.List;

import chess.movements.Movement;

public record MatchAnalysis(String gameId, String initialFen, String status, String result, List<Movement> moves){}