package chess.movements;

/**
 * Una jugada o rendición que no se puede aceptar. Se responde 422 con el código del contrato: INVALID_MOVE (jugada ilegal o mal escrita).
 */
public class MovementNotValidException extends RuntimeException{
	public static final String INVALID_MOVE = "INVALID_MOVE";

	private final String code;

	private MovementNotValidException(String code, String message){
		super(message);
		this.code = code;
	}

	public static MovementNotValidException illegalMove(String coordinateNotation){
		return new MovementNotValidException(INVALID_MOVE, "Jugada ilegal: " + coordinateNotation);
	}
	public String getCode(){
		return code;
	}
}
