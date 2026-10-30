package chess;

/** Cuerpo de POST /internal/logic/games/{id}/moves: { "uci": "e2e4" }. Con promoción: "e7e8q". */
public class MovementCreationEssentials{
    public String uci;

    public MovementCreationEssentials(){}

    public MovementCreationEssentials(String uci){
        this();
        this.uci = uci;
    }
}
