package com.prototipo.profile.events;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

import static com.prototipo.profile.config.RabbitTopology.MAX_RETRIES;
import static com.prototipo.profile.config.RabbitTopology.RETRY_COUNT_HEADER;
import static com.prototipo.profile.config.RabbitTopology.RETRY_EVENTS;
import static com.prototipo.profile.config.RabbitTopology.deadLetterQueue;

/**
 * Reintentos de la sección 17: el mensaje fallido va a retry.events con x-retry-count + 1 y vuelve
 * a su cola 5 s después. Si x-retry-count ya llegó a 5 y vuelve a fallar, va a la .dlq.
 */
@Component
public class RetryPublisher {

    private final RabbitTemplate rabbit;

    public RetryPublisher(RabbitTemplate rabbit) {
        this.rabbit = rabbit;
    }

    public void retryOrDeadLetter(Message message, String queue) {
        int count = retryCount(message);
        if (count >= MAX_RETRIES) {
            deadLetter(message, queue);
            return;
        }
        Message retry = MessageBuilder.fromMessage(message).setHeader(RETRY_COUNT_HEADER, count + 1).build();
        rabbit.send(RETRY_EVENTS, queue, retry);
    }

    public void deadLetter(Message message, String queue) {
        rabbit.send("", deadLetterQueue(queue), message);
    }

    static int retryCount(Message message) {
        Object value = message.getMessageProperties().getHeader(RETRY_COUNT_HEADER);
        if (value instanceof Number n) {
            return n.intValue();
        }
        if (value != null) {
            try {
                return Integer.parseInt(value.toString().trim());
            } catch (NumberFormatException ignored) {
                // encabezado ilegible: se cuenta como primer intento
            }
        }
        return 0;
    }
}
