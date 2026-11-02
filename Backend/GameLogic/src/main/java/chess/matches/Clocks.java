package chess.matches;

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
        setWhite(white);
        setBlack(black);
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

    public void setWhite(Integer white){
        this.white = white;
    }

    public void setBlack(Integer black){
        this.black = black;
    }

    public void setTurnStartedAt(String turnStartedAt){
        this.turnStartedAt = turnStartedAt;
    }

    public void setDeadline(String deadline){
        this.deadline = deadline;
    }
}