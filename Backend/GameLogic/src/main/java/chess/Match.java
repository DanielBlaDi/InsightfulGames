package chess;

import java.util.LinkedList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document
public class Match{
    @Id 
    private String id;
    private Long whitePlayerId;
    private Long blackPlayerId;
    private List<Movement> movements;

    public Match(Long whitePlayerId, Long blackPlayerId){
        this.whitePlayerId = whitePlayerId;
        this.blackPlayerId = blackPlayerId;
        this.movements = new LinkedList<>();
    }

    public void addMovement(Movement newMovement){
        this.movements.add(newMovement);
    }

    public String getId(){
        return id;
    }

    public Long getWhitePlayerId(){
        return whitePlayerId;
    }

    public Long getBlackPlayerId(){
        return blackPlayerId;
    }

    public List<Movement> getMovements(){
        return movements;
    }

    @Override public boolean equals(Object other){
        if(this == other){
            return true;
        }else if(!(other instanceof Match)){
            return false;
        }else{
            Match otherMatch = (Match)other;

            return this.id.equals(otherMatch.id) && 
                this.whitePlayerId == otherMatch.whitePlayerId &&
                this.blackPlayerId == otherMatch.blackPlayerId;
        }
    }

    @Override public String toString(){
        return "{id: " + id + ", whitePlayerId: " + whitePlayerId + ", blackPlayerId: " + blackPlayerId + "movements: " + movements + "}";
    }
}