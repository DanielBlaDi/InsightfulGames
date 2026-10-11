package chess;

import java.time.LocalDateTime;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Document;

@Document
public class Movement{
    @Id 
    private String id;
    private String boardFenBeforeMove;
    private String boardFenAfterMove;
    private String coordinateNotation;
    private Long playerId;
    private LocalDateTime dateTime;

    @PersistenceCreator
    public Movement(String boardFenBeforeMove, String boardFenAfterMove, String coordinateNotation, Long playerId, LocalDateTime dateTime){
        this.boardFenBeforeMove = boardFenBeforeMove;
        this.boardFenAfterMove = boardFenAfterMove;
        this.coordinateNotation = coordinateNotation;
        this.playerId = playerId;
        this.dateTime = dateTime;
    }

    public String getBoardFenBeforeMove(){
        return boardFenBeforeMove;
    }

    public String getBoardFenAfterMove(){
        return boardFenAfterMove;
    }

    public String getCoordinateNotation(){
        return coordinateNotation;
    }

    public Long getPlayerId(){
        return playerId;
    }

    public LocalDateTime getDateTime(){
        return dateTime;
    }

    @Override public boolean equals(Object other){
        if(this == other){
            return true;
        }else if(!(other instanceof Movement)){
            return false;
        }else{
            Movement otherMovement = (Movement)other;

            return this.boardFenAfterMove.equals(otherMovement.boardFenAfterMove) &&
                this.coordinateNotation.equals(otherMovement.coordinateNotation) &&
                this.playerId == otherMovement.playerId;
        }
    }
}