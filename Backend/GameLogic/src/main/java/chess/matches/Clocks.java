package chess.matches;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

import com.fasterxml.jackson.annotation.JsonIgnore;

import chess.constants.Color;

public class Clocks{
    private Integer white;
    private Integer black;
    private String turnStartedAt;
    private String deadline;

    public Clocks(){
        super();
    }

    public Clocks(Integer white, Integer black){
        this();
        this.white = white;
        this.black = black;
    }

    public Clocks(Integer white, Integer black, String turnStartedAt, String deadline){
        this(white, black);
        this.turnStartedAt = turnStartedAt;
        this.deadline = deadline;
    }

    public Integer getWhite(){
        return white;
    }

    public Integer getBlack(){
        return black;
    }

    public String getTurnStartedAt(){
        return turnStartedAt;
    }

    public String getDeadline(){
        return deadline;
    }

    /** Lógica interna: no forma parte del JSON de clocks (contrato, 11.4.1). */
    @JsonIgnore
    public boolean isTimedOut(){
        if(this.deadline != null){
            return Instant.parse(deadline).isBefore(Instant.now());
        }else{
            return false;
        }
    }

    /** Sets the start of the turn to now and calculates the deadline */
    public void startClock(){
        if(this.white != null){ //white can be the bot
            Instant turnStart = Instant.now();

            this.turnStartedAt = turnStart.toString();
            this.deadline = turnStart.plusMillis(this.white).toString(); //Match always starts on white
        }
    }

    public void endTurn(String nextTurnColor, Instant turnEndedAt){
        if(nextTurnColor.equals(Color.BLACK.toString())){
            if(this.white != null){
                this.white -= (int)(ChronoUnit.MILLIS.between(Instant.parse(turnStartedAt), turnEndedAt));
            }

            if(this.black != null){
                Instant turnStartInstant = Instant.now();
                this.turnStartedAt = turnStartInstant.toString();
                this.deadline = turnStartInstant.plusMillis(this.black).toString();
            }else{
                this.turnStartedAt = null;
                this.deadline = null;
            }
        }else{
            if(this.black != null){
                this.black -= (int)(ChronoUnit.MILLIS.between(Instant.parse(turnStartedAt), turnEndedAt));
            }

            if(this.white != null){
                Instant turnStartInstant = Instant.now();
                this.turnStartedAt = turnStartInstant.toString();
                this.deadline = turnStartInstant.plusMillis(this.white).toString();
            }else{
                this.turnStartedAt = null;
                this.deadline = null;
            }
        }
    }
}