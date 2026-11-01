package chess;

import java.util.List;

/** Cuerpo de POST /internal/logic/games*/
public record CreateGameRequest(String mode, TimeControl timeControl, String visibility, Integer botLevel, String matchId, List<Player> participants){}
