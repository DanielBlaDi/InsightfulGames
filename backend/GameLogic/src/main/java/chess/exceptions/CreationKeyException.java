package chess.exceptions;

/** HTTP 409 When finding a match with the same creationKey but different requestFingerprint*/
public class CreationKeyException extends ExceptionWithNamedCode{
    public static final String IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED";

    private CreationKeyException(String code, String message){
        super(code, message);
    }

    public static CreationKeyException keyReused(){
		return new CreationKeyException(IDEMPOTENCY_KEY_REUSED, "La clave de idempotencia ya existe con otro cuerpo");
	}
}