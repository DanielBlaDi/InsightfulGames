package chess.exceptions;

/** HTTP 409 error when trying to analyze a match that's not finished */
public class MatchNotFinishedException extends ExceptionWithNamedCode{
    public static final String GAME_NOT_FINISHED = "GAME_NOT_FINISHED";

    private MatchNotFinishedException(String code, String message){
		super(code, message);
	}

    public static MatchNotFinishedException notFinished(){
		return new MatchNotFinishedException(GAME_NOT_FINISHED, "No se puede analizar una partida que no se ha terminado");
	}
}