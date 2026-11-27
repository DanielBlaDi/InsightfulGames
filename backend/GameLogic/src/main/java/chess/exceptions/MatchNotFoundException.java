package chess.exceptions;

/** La partida no existe. Se responde 404 GAME_NOT_FOUND. */
public class MatchNotFoundException extends ExceptionWithNamedCode{
	public static final String GAME_NOT_FOUND = "GAME_NOT_FOUND";

	private MatchNotFoundException(String code, String message){
		super(code, message);
	}

	public static MatchNotFoundException notFound(String gameId){
		return new MatchNotFoundException(GAME_NOT_FOUND, "La partida " + gameId + " no existe");
	}
}
