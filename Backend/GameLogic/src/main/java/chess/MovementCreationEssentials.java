package chess;

public class MovementCreationEssentials{
    public String boardFenBeforeMove;
    public String coordinateNotation;
    public Long playerId;

    public MovementCreationEssentials(){}

    public MovementCreationEssentials(String boardFenBeforeMove){
        this();
        this.boardFenBeforeMove = boardFenBeforeMove;
    }

    public MovementCreationEssentials(String boardFenBeforeMove, String coordinateNotation, Long playerId){
        this(boardFenBeforeMove);
        this.coordinateNotation = coordinateNotation;
        this.playerId = playerId;
    } 
}