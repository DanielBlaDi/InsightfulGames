package chess;

/** Cuerpo de POST /logic/games (contrato, sección 3.5). botLevel y playerColor solo se usan en vs_bot. */
public record CreateGameRequest(String userId, String mode, Integer botLevel, String playerColor){
}
