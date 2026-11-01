package chess;

/** La lista de participantes no corresponde al modo. Responde 422 PARTICIPANTS_INVALID. */
public class ParticipantsInvalidException extends RuntimeException{
	ParticipantsInvalidException(String message){
		super(message);
	}
}
