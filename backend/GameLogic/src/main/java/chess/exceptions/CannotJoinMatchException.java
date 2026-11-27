package chess.exceptions;

/** HTTP 409 Represents trying to join a multiplayer Match that's no longer waiting for someone to join or trying to join as someone who's already on the Match. */
public class CannotJoinMatchException extends ExceptionWithNamedCode{
    public static final String GAME_NOT_WAITING = "GAME_NOT_WAITING";
    public static final String ALREADY_PARTICIPANT = "ALREADY_PARTICIPANT";

    private CannotJoinMatchException(String code, String message){
        super(code, message);
    }

    public static CannotJoinMatchException notWaiting(){
		return new CannotJoinMatchException(GAME_NOT_WAITING, "La partida no está esperando que un nuevo participante se una");
	}

    public static CannotJoinMatchException alreadyParticipant(){
		return new CannotJoinMatchException(ALREADY_PARTICIPANT, "El usuario ya está participando en la partida");
	}
}