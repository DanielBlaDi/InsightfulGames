package chess;

public class MovementCreationEssentials{
    public String boardFenBeforeMove;
    public String coordinateNotation;
    public Long playerId;

    public MovementCreationEssentials(String boardFenBeforeMove, String coordinateNotation, Long playerId){
        this.boardFenBeforeMove = boardFenBeforeMove;
        this.coordinateNotation = coordinateNotation;
        this.playerId = playerId;
    }
}