package chess.matches;

import java.util.List;

/**
 * Cuerpo de POST /internal/logic/games (contrato, 11.4.5). matchId, creationKey y
 * requestFingerprint solo existen en multijugador.
 */
public record CreateMatchRequest(String mode, TimeControl timeControl, String visibility, Integer botLevel, String matchId, List<Participant> participants, String creationKey, String requestFingerprint){}
