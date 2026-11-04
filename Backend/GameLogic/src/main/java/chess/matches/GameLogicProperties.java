package chess.matches;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** WAITING_TIMEOUT_MINUTES (contrato, 11.5): plazo de una partida multijugador en waiting. */
@ConfigurationProperties(prefix = "game")
public record GameLogicProperties(Integer waitingTimeoutMinutes){

    public GameLogicProperties{
        if(waitingTimeoutMinutes == null || waitingTimeoutMinutes < 1){
            throw new IllegalArgumentException("WAITING_TIMEOUT_MINUTES debe ser un entero mayor que 0");
        }
    }

    public Duration waitingTimeout(){
        return Duration.ofMinutes(waitingTimeoutMinutes);
    }
}
