package chess;

import java.time.Instant;
import java.util.Objects;

import org.springframework.data.annotation.PersistenceCreator;

/** Una jugada ya hecha, guardada dentro del documento de la partida*/
public class Movement{
    /**
     * Número de jugada, desde 1 (media jugada)
     */
    private int ply;

    /**
     * Notación para mostrar al usuario, p. ej. "e4"
     */
    private String san;

    /**
     * Notación UCI, p. ej. "e2e4" (con promoción: "e7e8q")
     */
    private String uci;

    /**
     * Estado del tablero en notación FEN después de la jugada
     */
    private String fenAfter;

    /**
     * El tiempo en el que se realizó la jugada
     */
    private Instant timestamp;

    @PersistenceCreator
    public Movement(int ply, String san, String uci, String fenAfter, Instant timestamp){
        this.ply = ply;
        this.san = san;
        this.uci = uci;
        this.fenAfter = fenAfter;
        this.timestamp = timestamp;
    }

    public int getPly(){
        return ply;
    }

    public String getSan(){
        return san;
    }

    public String getUci(){
        return uci;
    }

    public String getFenAfter(){
        return fenAfter;
    }

    public Instant getTimestamp(){
        return timestamp;
    }

    @Override public boolean equals(Object other){
        if(this == other){
            return true;
        }else if(!(other instanceof Movement)){
            return false;
        }else{
            Movement otherMovement = (Movement)other;

            return this.ply == otherMovement.ply &&
                Objects.equals(this.uci, otherMovement.uci) &&
                Objects.equals(this.fenAfter, otherMovement.fenAfter);
        }
    }

    @Override public int hashCode(){
        return Objects.hash(ply, uci, fenAfter);
    }

    @Override public String toString(){
        return ply + ". " + san + " (" + uci + ")";
    }
}
