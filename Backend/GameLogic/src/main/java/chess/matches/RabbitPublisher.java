package chess.matches;

import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

import tools.jackson.databind.ObjectMapper;

@Service
public class RabbitPublisher{
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

    private void sendWithRetry(Message message, String eventId, int attempt){

        CorrelationData correlationData = new CorrelationData(eventId);

        rabbitTemplate.send(
            "game.events", 
            "game.finished",
            message,
            correlationData
        );

        correlationData.getFuture().whenComplete((confirm, exception) -> {

            if(exception == null && confirm.ack()){
                return;
            }

            if(attempt >= 5){
                return;
            }

            int delay = (int)Math.pow(2, attempt);

            ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(1);
            scheduler.schedule(() -> sendWithRetry(message, eventId, attempt + 1),
                delay,
                TimeUnit.SECONDS
            );
        });
    }
}