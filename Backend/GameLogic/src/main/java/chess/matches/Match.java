package chess.matches;

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

import chess.constants.Color;
import chess.constants.Mode;
import chess.constants.Status;
import chess.movements.Movement;

/**
 * Una partida. Es el documento de la colección "games": el mismo GameState
 * con _id = gameId y el campo extra initialFen. legalMoves no se guarda, se calcula al responder
 * (ver MatchAssembler).
 */
@Document(collection = "games")
public class Match{
    public static final String ANONYMOUS_USER_ID = "00000000-0000-0000-0000-000000000000";

    /**
     * gameId: UUID v4 en texto
     */
    @Id
    private String gameId;

    /**
     * "local" o "vs_bot"
     */
    private String mode;

    /**
     * Indica si usuarios distintos a los participantes pueden ver esta partida, puede ser "private" o "shared"
     */
    private String visibility;

    /**
     * La id que utiliza Multiplayer para cada partida
     */
    private String matchId;

    /**
     * Los jugadores que hacen parte de esta partida
     */
    private List<Participant> participants;

    /**
     * 1 a 20; solo en vs_bot, null de lo contrario
     */
    private Integer botLevel;
        
    /**
     * Configuración del reloj de la partida, el tiempo inicial en minutos
     */
    private TimeControl timeControl;

    /**
     * Indica el tiempo en milisegundos restante para cada jugador, se mantiene y modifica a lo largo de los turnos. Además indica el tiempo en el que inició la partida y el máximo para terminar.
     */
    private Clocks clocks;

    /**
     * "waiting" o "in_progress" o "finished"
     */
    private String status;

    /**
     * "white" o "black", indica qué jugador tiene el turno actualmente
     */
    private String turn;

    /**
     * Estado del tablero en notación FEN
     */
    private String fen;

    /**
     * Estado del tablero en notación FEN al iniciar la partida
     */
    private String initialFen;

    /**
     * Lista de movimientos que se han realizado en esta partida
    */
    @Field("moves") //En Mongo el campo se llama "moves"
    private List<Movement> movements;

    /**
     * Indica el color del jugador que pidió un empate, null si no se pidió empate
     */
    private String drawOffer;

    /**
     * Versión de la partida, para mantener consistencia con operaciones que modifiquen a la partida
     */
    private int expectedVersion;

    /**
     * "white" o "black" o "draw" o null (si la partida no ha terminado)
     */
    private String result;

    /**
     * "checkmate" o "stalemate" o "resignation" o "draw" o null (si la partida sigue)
     */
    private String endReason;

    /**
     * El tiempo de inicio de la partida
     */
    private Instant createdAt;

    /**
     * El tiempo de fin de la partida, null mientras la partida sigue
     */
    private Instant finishedAt;

    /** Lo usa Spring Data para reconstruir la partida desde Mongo. */
    public Match(){
        this.movements = new LinkedList<>();
    }

    /** Crea una partida nueva en la posición inicial. Game Logic genera gameId y createdAt. */
    public Match(String mode, TimeControl timeControl, String visibility, Integer botLevel, String matchId, List<Participant> participants){
        this();
        this.gameId = UUID.randomUUID().toString();

        this.mode = mode;
        this.visibility = visibility;
        this.matchId = matchId;
        this.participants = participants;
        this.botLevel = botLevel;
        this.timeControl = timeControl;

        if(timeControl != null){
            if(mode.equals(Mode.VS_BOT.toString())){
                if(participants.get(0).color().equals(Color.WHITE.toString())){
                    this.clocks = new Clocks(timeControl.minutes()*60000, null);
                }else{
                    this.clocks = new Clocks(null, timeControl.minutes()*60000);
                }
            }else{
                this.clocks = new Clocks(timeControl.minutes()*60000, timeControl.minutes()*60000);
            }
        }

        this.status = mode.equals(Mode.MULTIPLAYER.toString()) ? Status.WAITING.toString() : Status.IN_PROGRESS.toString();
        this.turn = Color.WHITE.toString();
        this.fen = ChessRules.START_FEN;
        this.initialFen = ChessRules.START_FEN;
        this.drawOffer = null;
        this.expectedVersion = 0;
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

    /** Changes the user's id to ANONYMOUS_USER_ID in this Match, works even if both participants are the same user*/
    public void anonymizeUser(String userId){
        for(int i=0; i<participants.size(); i++){
            if(participants.get(i).userId().equals(userId)){
                participants.set(i, new Participant(ANONYMOUS_USER_ID, participants.get(i).color()));
            }
        }
    }

    /** Cierra la partida */
    public void finish(String result, String endReason){
        this.status = Status.FINISHED.toString();
        this.result = result;
        this.endReason = endReason;
        this.finishedAt = now();
    }

    public boolean isFinished(){
        return Status.FINISHED.toString().equals(status);
    }

    /** Las jugadas ya hechas en UCI, en orden. Con ellas e initialFen se reconstruye la posición. */
    public List<String> playedUciMoves(){
        List<String> uciMoves = new ArrayList<>();
        for(Movement movement : movements){
            uciMoves.add(movement.getUci());
        }
        return uciMoves;
    }

    public String getGameId(){
        return gameId;
    }

    public String getMode(){
        return mode;
    }

    public String getVisibility(){
        return visibility;
    }

    public String getMatchId(){
        return matchId;
    }

    public List<Participant> getParticipants(){
        return participants;
    }

    public Integer getBotLevel(){
        return botLevel;
    }

    public TimeControl getTimeControl(){
        return timeControl;
    }

    public Clocks getClocks(){
        return clocks;
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

    public String getDrawOffer(){
        return drawOffer;
    }

    public int getExpectedVersion(){
        return expectedVersion;
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

            return Objects.equals(this.gameId, otherMatch.gameId) && Objects.equals(this.participants, otherMatch.participants);
        }
    }

    @Override public int hashCode(){
        return Objects.hash((gameId != null ? gameId : matchId), participants);
    }

    @Override public String toString(){
        return "{gameId: " + gameId + ", participants: " + participants + ", mode: " + mode + ", status: " + status + ", movements: " + movements + "}";
    }
}
