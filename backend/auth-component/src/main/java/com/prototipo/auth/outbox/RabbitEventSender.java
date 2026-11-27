package com.prototipo.auth.outbox;

import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.core.ReturnedMessage;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Publica con confirmación del broker (publisher confirms) y con mandatory: si el broker no tiene
 * ninguna cola enlazada para la clave, devuelve el mensaje y el envío cuenta como fallido, así
 * el evento sigue pendiente en el outbox en lugar de perderse.
 */
@Component
public class RabbitEventSender implements EventSender {

    private final RabbitTemplate rabbit;
    private final long confirmTimeoutMs;
    private final Set<String> returned = ConcurrentHashMap.newKeySet();

    public RabbitEventSender(RabbitTemplate rabbit, @Value("${outbox.confirm-timeout-ms:5000}") long confirmTimeoutMs) {
        this.rabbit = rabbit;
        this.confirmTimeoutMs = confirmTimeoutMs;
        rabbit.setMandatory(true);
        rabbit.setReturnsCallback(this::onReturned);
    }

    @Override
    public void send(OutboxEvent event) {
        Message message = MessageBuilder.withBody(event.getPayload().getBytes(StandardCharsets.UTF_8))
                .setMessageId(event.getEventId())
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setContentEncoding("UTF-8")
                .setDeliveryMode(MessageDeliveryMode.PERSISTENT)
                .build();
        rabbit.invoke(operations -> {
            operations.send(event.getExchange(), event.getRoutingKey(), message);
            operations.waitForConfirmsOrDie(confirmTimeoutMs);
            return null;
        });
        // RabbitMQ entrega el mensaje devuelto antes que la confirmación.
        if (returned.remove(event.getEventId())) {
            throw new AmqpException("Sin cola enlazada para " + event.getExchange() + "/" + event.getRoutingKey());
        }
    }

    private void onReturned(ReturnedMessage message) {
        String id = message.getMessage().getMessageProperties().getMessageId();
        if (id != null) {
            returned.add(id);
        }
    }
}
