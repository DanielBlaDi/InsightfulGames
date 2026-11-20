package com.prototipo.profile.events;

import com.prototipo.profile.config.RabbitTopology;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

/**
 * Consumidores de profile.user-registered y profile.game-finished. El mensaje se confirma (ack)
 * al terminar el método: después de aplicarlo, o después de reenviarlo a retry.events o a la .dlq.
 * Si ese reenvío falla, la excepción hace que RabbitMQ lo vuelva a entregar.
 */
@Component
public class EventListeners {

    private static final Logger log = LoggerFactory.getLogger(EventListeners.class);

    private final EventParser parser;
    private final EventProcessor processor;
    private final RetryPublisher retries;

    public EventListeners(EventParser parser, EventProcessor processor, RetryPublisher retries) {
        this.parser = parser;
        this.processor = processor;
        this.retries = retries;
    }

    @RabbitListener(queues = RabbitTopology.USER_REGISTERED_QUEUE)
    public void onUserRegistered(Message message) {
        handle(message, RabbitTopology.USER_REGISTERED_QUEUE,
                () -> processor.userRegistered(parser.userRegistered(message.getBody())));
    }

    @RabbitListener(queues = RabbitTopology.GAME_FINISHED_QUEUE)
    public void onGameFinished(Message message) {
        handle(message, RabbitTopology.GAME_FINISHED_QUEUE,
                () -> processor.gameFinished(parser.gameFinished(message.getBody())));
    }

    void handle(Message message, String queue, Runnable work) {
        try {
            work.run();
        } catch (InvalidEventException e) {
            log.warn("Evento inválido en {}: {}. Se envía a la DLQ", queue, e.getMessage());
            retries.deadLetter(message, queue);
        } catch (RuntimeException e) {
            log.warn("Falló el procesamiento en {} (intento {}): {}", queue,
                    RetryPublisher.retryCount(message) + 1, e.toString());
            retries.retryOrDeadLetter(message, queue);
        }
    }
}
