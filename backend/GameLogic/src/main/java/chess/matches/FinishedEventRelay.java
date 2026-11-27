package chess.matches;

import java.time.Duration;
import java.time.Instant;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.ExchangeBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

/**
 * Reenvía los game.finished pendientes del outbox (Match.finishedEventPublished = false). Cubre el
 * broker caído y el reinicio del proceso antes de la confirmación. Deja un margen para no competir
 * con el envío inmediato que hace el controlador al terminar la partida.
 */
@Configuration
@EnableScheduling
public class FinishedEventRelay{
    private static final Logger log = LoggerFactory.getLogger(FinishedEventRelay.class);
    private static final Duration GRACE = Duration.ofSeconds(5);

    private final MatchRepository repository;
    private final RabbitPublisher publisher;

    public FinishedEventRelay(MatchRepository repository, RabbitPublisher publisher){
        this.repository = repository;
        this.publisher = publisher;
    }

    /** Mismo exchange y argumentos que declaran Profile/Stats y Multiplayer (topic, durable). */
    @Bean
    TopicExchange gameEventsExchange(){
        return ExchangeBuilder.topicExchange(RabbitPublisher.EXCHANGE).durable(true).build();
    }

    @Scheduled(initialDelayString = "${game-events.relay-initial-delay-ms:15000}", fixedDelayString = "${game-events.relay-interval-ms:10000}")
    public void relayPending(){
        Instant limit = Instant.now().minus(GRACE);
        int sent = 0;
        try{
            for(Match match : repository.findTop100ByFinishedEventPublishedFalseOrderByFinishedAtAsc()){
                if(match.getFinishedAt() != null && match.getFinishedAt().isBefore(limit)){
                    publisher.publishFinished(match);
                    sent++;
                }
            }
        }catch(RuntimeException e){
            log.warn("Relay de game.finished: {}", e.getMessage());
            return;
        }
        if(sent > 0){
            log.info("Relay de game.finished: {} evento(s) pendiente(s) reenviado(s)", sent);
        }
    }
}
