package chess.exceptions;

/** HTTP 422: acción de juego sobre una partida que ya terminó (contrato, 4.5 y 11.4.6). */
public class GameFinishedException extends ExceptionWithNamedCode{
	public static final String GAME_FINISHED = "GAME_FINISHED";

	private GameFinishedException(String code, String message){
		super(code, message);
	}

	public static GameFinishedException finished(){
		return new GameFinishedException(GAME_FINISHED, "La partida ya terminó");
	}
}
