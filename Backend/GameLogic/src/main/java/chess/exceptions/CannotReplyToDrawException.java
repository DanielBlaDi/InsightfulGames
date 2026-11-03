package chess.exceptions;

/** Exception for trying to accept or reject a draw when there's no draw being offered, or when the user trying to accept or reject is not allowed to do so*/
public class CannotReplyToDrawException extends ExceptionWithNamedCode{
	public static final String DRAW_NOT_OFFERED = "DRAW_NOT_OFFERED";
	public static final String DRAW_NOT_ALLOWED = "DRAW_NOT_ALLOWED";

	private CannotReplyToDrawException(String code, String message){
		super(code, message);
	}

	public static CannotReplyToDrawException notOffered(boolean isAccepting){
		return new CannotReplyToDrawException(DRAW_NOT_OFFERED, "No se puede " + (isAccepting ? "aceptar" : "rechazar") + " un empate que no se ha ofrecido");
	}

	public static CannotReplyToDrawException notAllowed(){
		return new CannotReplyToDrawException(DRAW_NOT_ALLOWED, "El usuario no tiene permitido realizar esta operación para este empate");
	}
}