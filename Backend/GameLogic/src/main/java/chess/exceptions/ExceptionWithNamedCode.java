package chess.exceptions;

/** HTTP 409 errors relating to draw operations */
public class ExceptionWithNamedCode extends RuntimeException{
    protected final String code;

    protected ExceptionWithNamedCode(String code, String message){
		super(message);
		this.code = code;
	}

	public String getCode(){
		return code;
	}
}