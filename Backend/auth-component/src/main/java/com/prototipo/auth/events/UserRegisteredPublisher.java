package com.prototipo.auth.events;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import tools.jackson.databind.json.JsonMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Publica user.registered (sección 17) después de confirmar el registro en MySQL: un registro
 * revertido nunca genera evento. Si RabbitMQ no responde, reintenta en memoria y, si sigue
 * fallando, el registro se mantiene y el evento se pierde (riesgo aceptado: no hay outbox).
 */
@Component
public class UserRegisteredPublisher {

    static final int ATTEMPTS = 3;
    private static final long PAUSE_MS = 200;
    private static final Logger log = LoggerFactory.getLogger(UserRegisteredPublisher.class);

    private final RabbitTemplate rabbit;
    private final JsonMapper mapper;
    private final Clock clock;

    public UserRegisteredPublisher(RabbitTemplate rabbit, JsonMapper mapper, Clock clock) {
        this.rabbit = rabbit;
        this.mapper = mapper;
        this.clock = clock;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onUserRegistered(UserRegistered registered) {
        Message message = toMessage(registered);
        for (int attempt = 1; attempt <= ATTEMPTS; attempt++) {
            try {
                rabbit.send(UserEventsTopology.USER_EVENTS, UserEventsTopology.USER_REGISTERED, message);
                return;
            } catch (RuntimeException e) {
                log.warn("No se pudo publicar user.registered (intento {} de {}): {}", attempt, ATTEMPTS, e.toString());
                pause(attempt);
            }
        }
        log.error("user.registered no se publicó para el usuario {}", registered.userId());
    }

    Message toMessage(UserRegistered registered) {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("eventId", UUID.randomUUID().toString());
        event.put("eventType", UserEventsTopology.USER_REGISTERED);
        event.put("occurredAt", Instant.now(clock).truncatedTo(ChronoUnit.SECONDS).toString());
        event.put("userId", registered.userId());
        event.put("username", registered.username());
        return MessageBuilder.withBody(mapper.writeValueAsBytes(event))
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setContentEncoding("UTF-8")
                .setDeliveryMode(MessageDeliveryMode.PERSISTENT)
                .build();
    }

    private static void pause(int attempt) {
        if (attempt == ATTEMPTS) {
            return;
        }
        try {
            Thread.sleep(PAUSE_MS * attempt);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
