package chess.matches;

/** HTTP 409 error when trying to analyze a match that's not finished */
public class MatchNotFinishedException extends RuntimeException{
    public static final String GAME_NOT_FINISHED = "GAME_NOT_FINISHED";

    private final String code;

    private MatchNotFinishedException(String code, String message){
		super(message);
		this.code = code;
	}

    public static MatchNotFinishedException notFinished(){
		return new MatchNotFinishedException(GAME_NOT_FINISHED, "No se puede analizar una partida que no se ha terminado");
	}
	public String getCode(){
		return code;
	}
}