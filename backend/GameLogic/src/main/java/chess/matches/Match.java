package chess.matches;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.index.Indexed;
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
@CompoundIndex(def = "{'participants.userId': 1, 'createdAt': -1}")
@CompoundIndex(def = "{'status': 1, 'clocks.deadline': 1}")
@CompoundIndex(def = "{'status': 1, 'createdAt': 1}")
public class Match{
    public static final String ANONYMOUS_USER_ID = "00000000-0000-0000-0000-000000000000";
    private static final int WAITING_TIMEOUT_MINUTES = 2;

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
    @Indexed(partialFilter = "{'matchId' : {'$type' : 'string'}}")
    private String matchId;

    /**
     * Únicamente presente en partidas multijugador, un sha256 hex creado por Multiplayer para evitar crear partidas duplicadas
     */
    @Indexed(partialFilter = "{'creationKey' : {'$type' : 'string'}}")
    private String creationKey;

    /**
     * Únicamente presente en partidas multijugador, un sha256 hex creado por Multiplayer para evitar crear partidas duplicadas
     */
    private String requestFingerprint;

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
    private int version;

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

    /**
     * Outbox de game.finished dentro del propio documento: se fija al terminar la partida y se guarda
     * en la misma escritura (atómica en MongoDB). El eventId es estable, así que reenviarlo tras un
     * reinicio no duplica estadísticas (los consumidores deduplican por eventId).
     */
    private String finishedEventId;

    /** false mientras game.finished no tenga confirmación del broker; null en partidas sin terminar o antiguas. */
    private Boolean finishedEventPublished;

    /** Lo usa Spring Data para reconstruir la partida desde Mongo. */
    public Match(){
        this.movements = new LinkedList<>();
    }

    /** Crea una partida nueva en la posición inicial. Game Logic genera gameId y createdAt. */
    public Match(String mode, TimeControl timeControl, String visibility, Integer botLevel, String matchId, String creationKey, String requestFingerprint, List<Participant> participants){
        this();
        this.gameId = UUID.randomUUID().toString();

        this.mode = mode;
        this.visibility = visibility;
        this.matchId = matchId;
        this.creationKey = creationKey;
        this.requestFingerprint = requestFingerprint;
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
        this.version = 0;
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

    public void addParticipant(Participant participant){
        this.participants.add(participant);
    }

    /** Changes the user's id to ANONYMOUS_USER_ID in this Match, works even if both participants are the same user. Additionally removes creationKey and requestFingerprint, as they are linked to the user who created the match if it is a multiplayer one*/
    public void anonymize(String userId){
        for(int i=0; i<participants.size(); i++){
            if(participants.get(i).userId().equals(userId)){
                participants.set(i, new Participant(ANONYMOUS_USER_ID, participants.get(i).color()));
            }
        }

        this.creationKey = null;
        this.requestFingerprint = null;
    }

    public boolean canBeOperatedOn(){
        return !Status.FINISHED.toString().equals(status) && !Status.WAITING.toString().equals(status);
    }

    /** Cierra la partida */
    public void finish(String result, String endReason){
        this.status = Status.FINISHED.toString();
        this.result = result;
        this.endReason = endReason;
        this.finishedAt = now();
        if(this.finishedEventId == null){
            this.finishedEventId = UUID.randomUUID().toString();
            this.finishedEventPublished = false;
        }
    }

    public String getFinishedEventId(){
        return finishedEventId;
    }

    public Boolean getFinishedEventPublished(){
        return finishedEventPublished;
    }

    public void finishAndUpdateVersion(String result, String endReason){
        this.finish(result, endReason);
        this.version++;
    }

    public boolean isFinished(){
        return Status.FINISHED.toString().equals(status);
    }

    public boolean isWaiting(){
        return Status.WAITING.toString().equals(status);
    }

    public boolean isExpiredFromWaiting(){
        return ChronoUnit.MINUTES.between(createdAt, Instant.now()) > WAITING_TIMEOUT_MINUTES;
    }

    /** Checks whether the Match is timed out or not, takes into account when the Match doesn't have a clock */
    public boolean isTimedOut(){
        if(this.clocks != null){
            return this.clocks.isTimedOut();
        }else{
            return false;
        }
    }

    /** Las jugadas ya hechas en UCI, en orden. Con ellas e initialFen se reconstruye la posición. */
    public List<String> playedUciMoves(){
        List<String> uciMoves = new ArrayList<>();
        for(Movement movement : movements){
            uciMoves.add(movement.getUci());
        }
        return uciMoves;
    }

    /** Checks whether there's a clock and starts it if there is */
    public void startClock(){
        if(this.clocks != null){
            this.clocks.startClock();
        }
    }

    public void updateVersion(){
        this.version++;
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

    public String getCreationKey(){
        return creationKey;
    }

    public String getRequestFingerPrint(){
        return requestFingerprint;
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

    public int getVersion(){
        return version;
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

    public void setStatus(String status){
        this.status = status;
    }

    public void setVisibility(String visibility){
        this.visibility = visibility;
    }

    public void setDrawOffer(String drawOffer){
        this.drawOffer = drawOffer;
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
