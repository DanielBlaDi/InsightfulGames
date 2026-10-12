package chess;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

/**
 * Una partida. Es el documento de la colección "games" (contrato, sección 3.8): el mismo GameState
 * con _id = gameId y el campo extra initialFen. legalMoves no se guarda, se calcula al responder
 * (ver MatchAssembler).
 */
@Document(collection = "games")
public class Match{
    public static final String MODE_LOCAL = "local";
    public static final String MODE_VS_BOT = "vs_bot";

    public static final String STATUS_IN_PROGRESS = "in_progress";
    public static final String STATUS_FINISHED = "finished";

    @Id
    private String id;                  // gameId: UUID v4 en texto
    private String userId;              // UUID v4 en texto
    private String mode;                // local | vs_bot
    private Integer botLevel;           // 1 a 20; solo en vs_bot, null en local
    private String playerColor;         // white | black; solo en vs_bot, null en local
    private String status;              // in_progress | finished
    private String turn;                // white | black
    private String fen;                 // posición actual
    private String initialFen;          // posición con la que empezó la partida
    @Field("moves")
    private List<Movement> movements;   // en Mongo y en el JSON del contrato el campo se llama "moves"
    private String result;              // white | black | draw | null (si la partida sigue)
    private String endReason;           // checkmate | stalemate | resignation | draw | null (si la partida sigue)
    private Instant createdAt;
    private Instant finishedAt;         // null mientras la partida sigue

    /** Lo usa Spring Data para reconstruir la partida desde Mongo. */
    public Match(){
        this.movements = new LinkedList<>();
    }

    /** Crea una partida nueva en la posición inicial. Game Logic genera gameId y createdAt. */
    public Match(String userId, String mode, Integer botLevel, String playerColor){
        this();
        this.id = UUID.randomUUID().toString();
        this.userId = userId;
        this.mode = mode;
        this.botLevel = botLevel;
        this.playerColor = playerColor;
        this.status = STATUS_IN_PROGRESS;
        this.turn = "white";
        this.initialFen = ChessRules.START_FEN;
        this.fen = ChessRules.START_FEN;
        this.createdAt = now();
    }

    /** Mongo guarda las fechas en milisegundos; se trunca aquí para que lo guardado y lo devuelto coincidan. */
    private static Instant now(){
        return Instant.now().truncatedTo(ChronoUnit.MILLIS);
    }

    /** Registra una jugada ya validada: actualiza la lista de jugadas, el FEN actual y el turno. */
    public void addMovement(Movement newMovement, String turnAfterMove){
        this.movements.add(newMovement);
        this.fen = newMovement.getFenAfter();
        this.turn = turnAfterMove;
    }

    /** Cierra la partida (jaque mate, ahogado, tablas o abandono). */
    public void finish(String result, String endReason){
        this.status = STATUS_FINISHED;
        this.result = result;
        this.endReason = endReason;
        this.finishedAt = now();
    }

    public boolean isFinished(){
        return STATUS_FINISHED.equals(status);
    }

    /** Las jugadas ya hechas en UCI, en orden. Con ellas y initialFen se reconstruye la posición. */
    public List<String> playedUciMoves(){
        List<String> uciMoves = new ArrayList<>();
        for(Movement movement : movements){
            uciMoves.add(movement.getUci());
        }
        return uciMoves;
    }

    public String getId(){
        return id;
    }

    public String getUserId(){
        return userId;
    }

    public String getMode(){
        return mode;
    }

    public Integer getBotLevel(){
        return botLevel;
    }

    public String getPlayerColor(){
        return playerColor;
    }

    public String getStatus(){
        return status;
    }

    public String getTurn(){
        return turn;
    }

    public String getFen(){
        return fen;
    }

    public String getInitialFen(){
        return initialFen;
    }

    public List<Movement> getMovements(){
        return movements;
    }

    public String getResult(){
        return result;
    }

    public String getEndReason(){
        return endReason;
    }

    public Instant getCreatedAt(){
        return createdAt;
    }

    public Instant getFinishedAt(){
        return finishedAt;
    }

    @Override public boolean equals(Object other){
        if(this == other){
            return true;
        }else if(!(other instanceof Match)){
            return false;
        }else{
            Match otherMatch = (Match)other;

            return Objects.equals(this.id, otherMatch.id) && Objects.equals(this.userId, otherMatch.userId);
        }
    }

    @Override public int hashCode(){
        return Objects.hash(id, userId);
    }

    @Override public String toString(){
        return "{id: " + id + ", userId: " + userId + ", mode: " + mode + ", status: " + status + ", movements: " + movements + "}";
    }
}
