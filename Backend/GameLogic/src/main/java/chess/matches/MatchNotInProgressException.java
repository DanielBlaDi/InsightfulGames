package chess.matches;

public class MatchNotInProgressException extends RuntimeException{
	public static final String GAME_NOT_IN_PROGRESS = "GAME_NOT_IN_PROGRESS";

	private final String code;

	private MatchNotInProgressException(String code, String message){
		super(message);
		this.code = code;
	}

	public static MatchNotInProgressException matchNotInProgress(){
		return new MatchNotInProgressException(GAME_NOT_IN_PROGRESS, "La partida no está en progreso");
	}

	public String getCode(){
		return code;
	}
}
