package chess.exceptions;

/** La petición no es válida: faltan campos o tienen formato inválido. Se responde 400 VALIDATION_ERROR. */
public class RequestNotValidException extends ExceptionWithNamedCode{
	public static final String VALIDATION_ERROR = "VALIDATION_ERROR";

	private RequestNotValidException(String code, String message){
		super(code, message);
	}

	public static RequestNotValidException notValid(String message){
		return new RequestNotValidException(VALIDATION_ERROR, message);
	}
}
