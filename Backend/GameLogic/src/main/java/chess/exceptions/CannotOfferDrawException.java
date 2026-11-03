package chess.exceptions;

/** HTTP 409 errors relating to draw operations */
public class CannotOfferDrawException extends ExceptionWithNamedCode{
    public static final String DRAW_ALREADY_OFFERED = "DRAW_ALREADY_OFFERED";

    private CannotOfferDrawException(String code, String message){
        super(code, message);
    }

    public static CannotOfferDrawException alreadyOffered(){
		return new CannotOfferDrawException(DRAW_ALREADY_OFFERED, "No se puede ofrecer un empate cuando ya hay uno en curso");
	}
}