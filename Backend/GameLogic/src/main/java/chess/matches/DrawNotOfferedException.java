package chess.matches;

/** Exception for trying to accept or reject a draw when there's no draw being offered */
public class DrawNotOfferedException extends RuntimeException{
	public static final String DRAW_NOT_OFFERED = "DRAW_NOT_OFFERED";

    private final String code;

    private DrawNotOfferedException(String code, String message){
		super(message);
		this.code = code;
	}

	public static DrawNotOfferedException notOffered(boolean isAccepting){
		return new DrawNotOfferedException(DRAW_NOT_OFFERED, "No se puede " + (isAccepting ? "aceptar" : "rechazar") + " un empate que no se ha ofrecido");
	}

	public String getCode(){
		return code;
	}
}