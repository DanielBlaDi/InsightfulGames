package chess.matches;

import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

import tools.jackson.databind.ObjectMapper;

@Service
public class RabbitPublisher{
    private static final Logger log = LoggerFactory.getLogger(RabbitPublisher.class);
    private static final int MAX_RETRIES = 5;

    /** Un solo hilo (daemon) para todos los reintentos: antes se creaba un pool nuevo en cada uno. */
    private static final ScheduledExecutorService RETRIES = Executors.newSingleThreadScheduledExecutor(runnable -> {
        Thread thread = new Thread(runnable, "game-finished-retry");
        thread.setDaemon(true);
        return thread;
    });

    private final ObjectMapper objectMapper;
    private final RabbitTemplate rabbitTemplate;

    public RabbitPublisher(ObjectMapper objectMapper, RabbitTemplate rabbitTemplate){
        this.objectMapper = objectMapper;
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishMatchFinishedMessage(MatchFinishedMessage messageInformation){

        String eventId = UUID.randomUUID().toString();

        byte[] body = objectMapper.writeValueAsBytes(messageInformation);

        Message message = MessageBuilder
            .withBody(body)
            .setContentType(MessageProperties.CONTENT_TYPE_JSON)
            .setMessageId(eventId)
            .build();

        sendWithRetry(message, eventId, 0);
    }

    /**
     * Envía game.finished y reintenta (1, 2, 4, 8, 16 s) si el broker no confirma o no está disponible.
     * Nunca lanza: la partida ya terminó y se guarda aunque RabbitMQ esté caído; si fallara aquí, la
     * petición respondería 500 y, en un jaque mate, la jugada no llegaría a guardarse.
     */
    void sendWithRetry(Message message, String eventId, int attempt){

        CorrelationData correlationData = new CorrelationData(eventId);

        try{
            rabbitTemplate.send(
                "game.events",
                "game.finished",
                message,
                correlationData
            );
        }catch(AmqpException e){
            log.warn("No se pudo publicar game.finished {} (intento {}): {}", eventId, attempt + 1, e.getMessage());
            scheduleRetry(message, eventId, attempt);
            return;
        }

        correlationData.getFuture().whenComplete((confirm, exception) -> {

            if(exception == null && confirm.ack()){
                return;
            }

            scheduleRetry(message, eventId, attempt);
        });
    }

    private void scheduleRetry(Message message, String eventId, int attempt){
        if(attempt >= MAX_RETRIES){
            log.error("game.finished {} descartado tras {} intentos", eventId, attempt + 1);
            return;
        }

        int delay = (int)Math.pow(2, attempt);

        RETRIES.schedule(() -> sendWithRetry(message, eventId, attempt + 1),
            delay,
            TimeUnit.SECONDS
        );
    }
}