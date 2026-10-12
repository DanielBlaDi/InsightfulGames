package chess;

/**
 * Una jugada o rendición que no se puede aceptar. Se responde 422 con el código del contrato:
 * INVALID_MOVE (jugada ilegal o mal escrita) o GAME_FINISHED (la partida ya terminó).
 */
public class MovementNotValidException extends RuntimeException{
	public static final String INVALID_MOVE = "INVALID_MOVE";
	public static final String GAME_FINISHED = "GAME_FINISHED";

	private final String code;

	private MovementNotValidException(String code, String message){
		super(message);
		this.code = code;
	}

	static MovementNotValidException illegalMove(String coordinateNotation){
		return new MovementNotValidException(INVALID_MOVE, "Jugada ilegal: " + coordinateNotation);
	}

	static MovementNotValidException matchFinished(){
		return new MovementNotValidException(GAME_FINISHED, "La partida ya terminó");
	}

	public String getCode(){
		return code;
	}
}
