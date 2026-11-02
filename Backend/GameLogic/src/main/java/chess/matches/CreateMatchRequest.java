package chess.matches;

import java.util.List;

/** Cuerpo de POST /internal/logic/games*/
public record CreateMatchRequest(String mode, TimeControl timeControl, String visibility, Integer botLevel, String matchId, List<Participant> participants){}
