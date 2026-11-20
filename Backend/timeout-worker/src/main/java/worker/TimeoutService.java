package worker;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

/**
 * Ciclo de cierre de partidas vencidas (contrato, 18.2 y 18.4), siempre por el gateway interno:
 * GET /internal/logic/games/expired?limit=N y, para cada partida, POST .../{id}/timeout (reloj
 * vencido) o POST .../{id}/expire (espera caducada), con { expectedVersion }.
 *
 * <p>Procesa en secuencia y no guarda estado: lo que no se cierra en un ciclo vuelve a aparecer
 * en la consulta siguiente. Un error en una partida no impide procesar las demás.
 */
@Service
public class TimeoutService{

    private static final Logger log = LoggerFactory.getLogger(TimeoutService.class);

    static final String GAMES = "/internal/logic/games";

    /** reason del contrato (clock, waiting) y el que hoy devuelve Game Logic (timeout, expired). */
    static final Set<String> CLOCK_REASONS = Set.of("clock", "timeout");
    static final Set<String> WAITING_REASONS = Set.of("waiting", "expired");

    /** Respuestas previstas cuando otra operación ya cambió la partida (contrato, 18.2). */
    static final Set<String> IGNORED_CODES =
        Set.of("VERSION_CONFLICT", "GAME_FINISHED", "CLOCK_NOT_EXPIRED", "WAITING_NOT_EXPIRED");

    /** Resultado de procesar una partida. */
    enum Outcome{
        /** Game Logic cerró la partida. */
        CLOSED,
        /** Error previsto: otra operación ya cambió la partida. */
        IGNORED,
        /** Otro 4xx: la petición no se aceptó. Se registra y se sigue. */
        REJECTED,
        /** 5xx: se registra y se reintenta en el ciclo siguiente. */
        FAILED,
        /** Elemento inválido o con reason desconocido. */
        SKIPPED,
        /** Gateway inalcanzable: se corta el ciclo y se reintenta en el siguiente. */
        UNREACHABLE
    }

    private final RestClient restClient;
    private final WorkerProperties properties;
    private final WorkerHealth health;

    public TimeoutService(RestClient restClient, WorkerProperties properties, WorkerHealth health){
        this.restClient = restClient;
        this.properties = properties;
        this.health = health;
    }

    @Scheduled(fixedDelayString = "${worker.poll-interval-seconds}", timeUnit = java.util.concurrent.TimeUnit.SECONDS)
    public void periodicallyTimeoutAndExpireMatches(){
        try{
            runCycle();
        }catch(RuntimeException e){
            // Nunca debe escapar: el planificador seguiría, pero el error quedaría sin contexto.
            log.error("Error inesperado en el ciclo de cierre", e);
        }finally{
            health.beat();
        }
    }

    /** Un ciclo completo. Devuelve cuántas partidas terminaron en cada resultado. */
    Map<Outcome, Integer> runCycle(){
        health.beat();
        Map<Outcome, Integer> counts = new java.util.EnumMap<>(Outcome.class);

        List<ExpiredQueryResponse> expired;
        try{
            expired = restClient.get()
                .uri(GAMES + "/expired?limit={limit}", properties.batchLimit())
                .retrieve()
                .body(new ParameterizedTypeReference<List<ExpiredQueryResponse>>(){});
        }catch(RestClientResponseException e){
            log.warn("GET {}/expired respondió {} {}: se reintenta en el siguiente ciclo",
                GAMES, e.getStatusCode().value(), errorCode(e));
            return counts;
        }catch(ResourceAccessException e){
            log.warn("Gateway interno no disponible al consultar partidas vencidas: {}", e.getMessage());
            return counts;
        }

        if(expired == null || expired.isEmpty()){
            return counts;
        }

        for(ExpiredQueryResponse match : expired){
            Outcome outcome;
            try{
                outcome = process(match);
            }catch(RuntimeException e){
                log.error("Error inesperado al procesar la partida {}", match == null ? null : match.gameId(), e);
                outcome = Outcome.FAILED;
            }
            health.beat();
            counts.merge(outcome, 1, Integer::sum);
            if(outcome == Outcome.UNREACHABLE){
                break; // si el gateway no responde, las demás partidas fallarían igual
            }
        }

        if(counts.getOrDefault(Outcome.CLOSED, 0) > 0 || log.isDebugEnabled()){
            log.info("Ciclo de cierre: {}", counts);
        }
        return counts;
    }

    Outcome process(ExpiredQueryResponse match){
        if(match == null || match.gameId() == null || match.gameId().isBlank() || match.version() == null){
            log.warn("Elemento inválido en la lista de partidas vencidas: {}", match);
            return Outcome.SKIPPED;
        }

        String action;
        if(CLOCK_REASONS.contains(match.reason())){
            action = "timeout";
        }else if(WAITING_REASONS.contains(match.reason())){
            action = "expire";
        }else{
            log.warn("Partida {} con reason desconocido: {}", match.gameId(), match.reason());
            return Outcome.SKIPPED;
        }

        try{
            restClient.post()
                .uri(GAMES + "/{id}/{action}", match.gameId(), action)
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("expectedVersion", match.version()))
                .retrieve()
                .toBodilessEntity();
            log.info("Partida {} cerrada con {} (versión {})", match.gameId(), action, match.version());
            return Outcome.CLOSED;
        }catch(RestClientResponseException e){
            int status = e.getStatusCode().value();
            String code = errorCode(e);
            if(e.getStatusCode().is4xxClientError()){
                if(IGNORED_CODES.contains(code)){
                    log.debug("Partida {}: {} ignorado ({})", match.gameId(), action, code);
                    return Outcome.IGNORED;
                }
                log.warn("Partida {}: {} rechazado con {} {}", match.gameId(), action, status, code);
                return Outcome.REJECTED;
            }
            log.warn("Partida {}: {} respondió {} {}; se reintenta en el siguiente ciclo",
                match.gameId(), action, status, code);
            return Outcome.FAILED;
        }catch(ResourceAccessException e){
            log.warn("Gateway interno no disponible al cerrar la partida {}: {}", match.gameId(), e.getMessage());
            return Outcome.UNREACHABLE;
        }
    }

    /** Código del cuerpo de error del contrato, o null si el cuerpo no tiene esa forma. */
    private static String errorCode(RestClientResponseException e){
        try{
            ErrorResponse body = e.getResponseBodyAs(ErrorResponse.class);
            return body == null || body.error() == null ? null : body.error().code();
        }catch(RuntimeException ignored){
            return null;
        }
    }
}
