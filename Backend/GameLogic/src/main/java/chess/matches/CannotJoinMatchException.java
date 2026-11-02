package chess.matches;

/** Represents trying to join a multiplayer Match that's no longer waiting for someone to join or trying to join as someone who's already on the Match. */
public class CannotJoinMatchException extends RuntimeException{
    private String errorCode;

    CannotJoinMatchException(String gameId, String errorCode){
        super("No es posible unirse a la partida " + gameId);
        this.errorCode = errorCode;
    }

    public String getErrorCode(){
        return errorCode;
    }
}