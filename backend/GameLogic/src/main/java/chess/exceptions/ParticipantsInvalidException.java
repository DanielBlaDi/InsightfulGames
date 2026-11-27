package chess.exceptions;

/** La lista de participantes no corresponde al modo. Responde 422 PARTICIPANTS_INVALID. */
public class ParticipantsInvalidException extends ExceptionWithNamedCode{
	public static final String PARTICIPANTS_INVALID = "PARTICIPANTS_INVALID";
	
	private ParticipantsInvalidException(String code, String message){
		super(code, message);
	}

	public static ParticipantsInvalidException participantsInvalid(String message){
		return new ParticipantsInvalidException(PARTICIPANTS_INVALID, message);
	}
}
