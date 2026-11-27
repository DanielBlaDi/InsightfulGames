package chess.matches;

import java.time.Instant;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

import tools.jackson.databind.ObjectMapper;

/**
 * Publica game.finished desde el outbox de la partida (Match.finishedEventId).
 *
 * Garantía: al menos una vez. La partida terminada y su evento pendiente se guardan juntos; aquí solo
 * se envía. Si RabbitMQ no confirma (caído, nack o mensaje sin cola), el evento sigue pendiente en
 * MongoDB y FinishedEventRelay lo reintenta, también después de reiniciar el proceso. Nunca lanza:
 * terminar una partida no depende de que el broker esté disponible.
 */
@Service
public class RabbitPublisher{
    private static final Logger log = LoggerFactory.getLogger(RabbitPublisher.class);
    static final String EXCHANGE = "game.events";
    static final String ROUTING_KEY = "game.finished";

    private final ObjectMapper objectMapper;
    private final RabbitTemplate rabbitTemplate;
    private final MongoTemplate mongoTemplate;

    public RabbitPublisher(ObjectMapper objectMapper, RabbitTemplate rabbitTemplate, MongoTemplate mongoTemplate){
        this.objectMapper = objectMapper;
        this.rabbitTemplate = rabbitTemplate;
        this.mongoTemplate = mongoTemplate;
    }

    /** Envía el game.finished pendiente de una partida YA guardada. Sin evento pendiente no hace nada. */
    public void publishFinished(Match match){
        String eventId = match.getFinishedEventId();
        if(eventId == null || Boolean.TRUE.equals(match.getFinishedEventPublished())){
            return;
        }

        Message message;
        try{
            message = MessageBuilder
                .withBody(objectMapper.writeValueAsBytes(toMessage(match)))
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setMessageId(eventId)
                .setDeliveryMode(MessageDeliveryMode.PERSISTENT)
                .build();
        }catch(RuntimeException e){
            log.error("No se pudo serializar game.finished {}", eventId, e);
            return;
        }

        CorrelationData correlation = new CorrelationData(eventId);
        try{
            rabbitTemplate.send(EXCHANGE, ROUTING_KEY, message, correlation);
        }catch(AmqpException e){
            log.warn("game.finished {} queda pendiente: {}", eventId, e.getMessage());
            return;
        }

        correlation.getFuture().whenComplete((confirm, error) -> {
            if(error == null && confirm != null && confirm.ack() && correlation.getReturned() == null){
                markPublished(match.getGameId(), eventId);
            }else{
                log.warn("game.finished {} sin confirmación del broker; queda pendiente", eventId);
            }
        });
    }

    /** Marca el evento como entregado solo si sigue siendo el mismo (actualización atómica en MongoDB). */
    void markPublished(String gameId, String eventId){
        mongoTemplate.updateFirst(
            Query.query(Criteria.where("_id").is(gameId).and("finishedEventId").is(eventId)),
            Update.update("finishedEventPublished", true),
            Match.class
        );
    }

    static MatchFinishedMessage toMessage(Match match){
        return new MatchFinishedMessage(
            match.getFinishedEventId(),
            ROUTING_KEY,
            Instant.now().toString(),
            match.getGameId(),
            match.getMatchId(),
            match.getMode(),
            match.getParticipants(),
            match.getResult(),
            match.getEndReason(),
            match.getFinishedAt().toString()
        );
    }
}
