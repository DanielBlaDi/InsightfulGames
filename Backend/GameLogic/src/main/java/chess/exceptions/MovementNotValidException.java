package chess.exceptions;

/**
 * Una jugada o rendición que no se puede aceptar. Se responde 422 con el código del contrato: INVALID_MOVE (jugada ilegal o mal escrita).
 */
public class MovementNotValidException extends ExceptionWithNamedCode{
	public static final String INVALID_MOVE = "INVALID_MOVE";

	private MovementNotValidException(String code, String message){
		super(code, message);
	}

	public static MovementNotValidException illegalMove(String coordinateNotation){
		return new MovementNotValidException(INVALID_MOVE, "Jugada ilegal: " + coordinateNotation);
	}
}
