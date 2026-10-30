package chess;

/** Cuerpo de POST /internal/logic/games/{id}/resign: { "side": "white" }. Es el bando que se rinde. */
public class MatchResultRequest{
    public String side;

    public MatchResultRequest(){}

    public MatchResultRequest(String side){
        this();
        this.side = side;
    }
}
