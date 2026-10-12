package chess;

import java.time.Instant;
import java.util.Objects;

import org.springframework.data.annotation.PersistenceCreator;

/** Una jugada ya hecha, guardada dentro del documento de la partida (elemento de "moves" en el contrato). */
public class Movement{
    private int ply;            // número de jugada, desde 1 (media jugada)
    private String san;         // notación para mostrar al usuario, p. ej. "e4"
    private String uci;         // notación UCI, p. ej. "e2e4" (con promoción: "e7e8q")
    private String fenAfter;    // posición después de la jugada
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
