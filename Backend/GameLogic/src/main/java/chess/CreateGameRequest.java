package chess;

/** Cuerpo de POST /internal/logic/games. botLevel y playerColor solo se usan en vs_bot. */
public record CreateGameRequest(String userId, String mode, Integer botLevel, String playerColor){
}
