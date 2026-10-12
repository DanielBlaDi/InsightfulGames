package chess;

import java.time.LocalDateTime;
import java.util.LinkedList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Document;

@Document
public class Match{
    @Id 
    private String id;
    private Long whitePlayerId;
    private Long blackPlayerId;
    private List<Movement> movements;
    private LocalDateTime createdAt;
    private String result;       // WHITE_WINS | BLACK_WINS | DRAW | null (if the match isn't over yet)
    private String resultReason; // CHECKMATE | STALEMATE | DRAW_RULE | RESIGNATION | null (if the match isn't over yet)

    public Match(){}

    @PersistenceCreator
    public Match(Long whitePlayerId, Long blackPlayerId){
        this();
        this.whitePlayerId = whitePlayerId;
        this.blackPlayerId = blackPlayerId;
        this.movements = new LinkedList<>();
        this.createdAt = LocalDateTime.now();
    }

    public Match(String id, Long whitePlayerId, Long blackPlayerId){
        this(whitePlayerId, blackPlayerId);
        this.id = id;
    }

    public void addMovement(Movement newMovement){
        this.movements.add(newMovement);
    }

    public void finish(String result, String resultReason){
        this.result = result;
        this.resultReason = resultReason;
    }

    public LocalDateTime getCreatedAt(){
        return createdAt;
    }

    public String getResult(){
        return result;
    }

    public String getResultReason(){
        return resultReason;
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