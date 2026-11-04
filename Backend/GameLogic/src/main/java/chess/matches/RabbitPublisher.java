package chess.matches;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

import tools.jackson.databind.ObjectMapper;

/**
 * Publica game.finished (contrato, 11.4.10 y 19.5): se llama después de guardar, nunca lanza y
 * nunca cambia la respuesta HTTP. Si el broker no confirma, reintenta en memoria a los 1, 2, 4, 8
 * y 16 segundos; después deja un log de error. Los reintentos no sobreviven a un reinicio.
 */
@Service
public class RabbitPublisher{
    private static final Logger log = LoggerFactory.getLogger(RabbitPublisher.class);
    static final int MAX_RETRIES = 5;

    private final ObjectMapper objectMapper;
    private final RabbitTemplate rabbitTemplate;
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor(runnable -> {
        Thread thread = new Thread(runnable, "game-finished-retry");
        thread.setDaemon(true);
        return thread;
    });

    public RabbitPublisher(ObjectMapper objectMapper, RabbitTemplate rabbitTemplate){
        this.objectMapper = objectMapper;
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishMatchFinishedMessage(MatchFinishedMessage event){
        try{
            Message message = MessageBuilder
                .withBody(objectMapper.writeValueAsBytes(event))
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setMessageId(event.eventId())
                .setDeliveryMode(MessageDeliveryMode.PERSISTENT)
                .build();
            sendWithRetry(message, event, 0);
        }catch(RuntimeException exception){
            log.error("No se pudo preparar game.finished de la partida {}", event.gameId(), exception);
        }
    }

    private void sendWithRetry(Message message, MatchFinishedMessage event, int attempt){
        CorrelationData correlationData = new CorrelationData(event.eventId());
        try{
            rabbitTemplate.send(RabbitConfig.GAME_EVENTS, RabbitConfig.GAME_FINISHED, message, correlationData);
        }catch(RuntimeException exception){
            // Broker caído o credenciales inválidas: send lanza antes de cualquier confirmación.
            retryLater(message, event, attempt, exception.toString());
            return;
        }

        correlationData.getFuture().whenComplete((confirm, exception) -> {
            if(exception == null && confirm != null && confirm.ack()){
                return;
            }
            String reason = exception != null ? exception.toString() : (confirm == null ? "sin confirmación" : confirm.reason());
            retryLater(message, event, attempt, reason);
        });
    }

    private void retryLater(Message message, MatchFinishedMessage event, int attempt, String reason){
        if(attempt >= MAX_RETRIES){
            log.error("game.finished de la partida {} (eventId {}) no se publicó tras {} reintentos: {}",
                event.gameId(), event.eventId(), MAX_RETRIES, reason);
            return;
        }
        long delay = 1L << attempt; // 1, 2, 4, 8, 16 s
        log.warn("game.finished de la partida {} no confirmado ({}); reintento en {} s", event.gameId(), reason, delay);
        scheduler.schedule(() -> sendWithRetry(message, event, attempt + 1), delay, TimeUnit.SECONDS);
    }
}
