package chess.matches;

/** La partida no existe. Se responde 404 GAME_NOT_FOUND. */
public class MatchNotFoundException extends RuntimeException{
	MatchNotFoundException(String id) {
		super("La partida no existe: " + id);
	}
}
