package chess.matches;

import java.util.List;

/**
 * Cuerpo de POST /internal/logic/games. creationKey y requestFingerprint los envía Multiplayer para
 * la idempotencia de la creación (Idempotency-Key): el nombre del campo JSON es requestFingerprint.
 */
public record CreateMatchRequest(
    String mode,
    TimeControl timeControl,
    String visibility,
    Integer botLevel,
    String matchId,
    List<Participant> participants,
    String creationKey,
    String requestFingerprint
) {}
