package worker;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/**
 * Salud del worker sin depender de Game Logic (contrato, 18.2): el ciclo registra actividad en
 * cada consulta y en cada partida. Si deja de hacerlo (planificador detenido o bloqueado), el
 * servicio deja de estar saludable aunque el servidor HTTP siga respondiendo.
 */
@Component
public class WorkerHealth{

    private final Clock clock;
    private final Duration staleAfter;
    private volatile Instant lastActivity;

    @Autowired
    public WorkerHealth(WorkerProperties properties){
        this(Clock.systemUTC(), properties.staleAfter());
    }

    WorkerHealth(Clock clock, Duration staleAfter){
        this.clock = clock;
        this.staleAfter = staleAfter;
        this.lastActivity = clock.instant();
    }

    public void beat(){
        lastActivity = clock.instant();
    }

    public boolean isHealthy(){
        return Duration.between(lastActivity, clock.instant()).compareTo(staleAfter) <= 0;
    }

    public Instant lastActivity(){
        return lastActivity;
    }
}
