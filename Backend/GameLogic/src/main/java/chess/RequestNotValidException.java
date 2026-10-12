package chess;

/** La petición no es válida: faltan campos o tienen formato inválido. Se responde 400 VALIDATION_ERROR. */
public class RequestNotValidException extends RuntimeException{
	RequestNotValidException(String message){
		super(message);
	}
}
