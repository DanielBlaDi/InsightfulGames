package chess.matches;

/** HTTP 409 errors relating to draw operations */
public class CannotOfferDrawException extends RuntimeException{
    public static final String DRAW_ALREADY_OFFERED = "DRAW_ALREADY_OFFERED";

    private final String code;

    private CannotOfferDrawException(String code, String message){
		super(message);
		this.code = code;
	}

    public static CannotOfferDrawException alreadyOffered(){
		return new CannotOfferDrawException(DRAW_ALREADY_OFFERED, "No se puede ofrecer un empate cuando ya hay uno en curso");
	}
	public String getCode(){
		return code;
	}
}