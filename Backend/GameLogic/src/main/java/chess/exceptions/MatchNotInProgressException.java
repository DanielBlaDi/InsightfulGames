package chess.exceptions;

public class MatchNotInProgressException extends ExceptionWithNamedCode{
	public static final String GAME_NOT_IN_PROGRESS = "GAME_NOT_IN_PROGRESS";

	private MatchNotInProgressException(String code, String message){
		super(code, message);
	}

	public static MatchNotInProgressException matchNotInProgress(){
		return new MatchNotInProgressException(GAME_NOT_IN_PROGRESS, "La partida no está en progreso");
	}
}
