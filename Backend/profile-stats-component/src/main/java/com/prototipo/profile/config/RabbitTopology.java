package com.prototipo.profile.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.ExchangeBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.ArrayList;
import java.util.List;

/**
 * Exchanges y colas de la sección 17 que usa Profile/Stats. Las declaraciones son idempotentes:
 * los demás servicios que usen los mismos exchanges deben declararlos con los mismos argumentos.
 */
@Configuration
public class RabbitTopology {

    public static final String USER_EVENTS = "user.events";
    public static final String GAME_EVENTS = "game.events";
    public static final String RETRY_EVENTS = "retry.events";

    public static final String USER_REGISTERED = "user.registered";
    public static final String GAME_FINISHED = "game.finished";

    public static final String USER_REGISTERED_QUEUE = "profile.user-registered";
    public static final String GAME_FINISHED_QUEUE = "profile.game-finished";

    /** Encabezado que cuenta los reenvíos (sección 17). */
    public static final String RETRY_COUNT_HEADER = "x-retry-count";
    public static final int MAX_RETRIES = 5;
    public static final int RETRY_DELAY_MS = 5000;

    /**
     * Cola de espera de cada consumidor. v9 define la espera (x-message-ttl=5000 con dead-letter a
     * la cola original), pero no su nombre: el sufijo .wait es propio de este servicio.
     */
    public static String waitQueue(String queue) {
        return queue + ".wait";
    }

    public static String deadLetterQueue(String queue) {
        return queue + ".dlq";
    }

    @Bean
    public Declarables profileTopology() {
        TopicExchange userEvents = ExchangeBuilder.topicExchange(USER_EVENTS).durable(true).build();
        TopicExchange gameEvents = ExchangeBuilder.topicExchange(GAME_EVENTS).durable(true).build();
        DirectExchange retryEvents = ExchangeBuilder.directExchange(RETRY_EVENTS).durable(true).build();

        List<org.springframework.amqp.core.Declarable> all = new ArrayList<>(List.of(userEvents, gameEvents, retryEvents));
        all.addAll(consumer(USER_REGISTERED_QUEUE, userEvents, USER_REGISTERED, retryEvents));
        all.addAll(consumer(GAME_FINISHED_QUEUE, gameEvents, GAME_FINISHED, retryEvents));
        return new Declarables(all);
    }

    /** Cola principal, su cola de espera para reintentos y su .dlq. */
    private static List<org.springframework.amqp.core.Declarable> consumer(
            String queueName, TopicExchange source, String routingKey, DirectExchange retryEvents) {
        Queue queue = QueueBuilder.durable(queueName).build();
        Queue wait = QueueBuilder.durable(waitQueue(queueName))
                .ttl(RETRY_DELAY_MS)
                .deadLetterExchange("")
                .deadLetterRoutingKey(queueName)
                .build();
        Queue dlq = QueueBuilder.durable(deadLetterQueue(queueName)).build();

        Binding main = BindingBuilder.bind(queue).to(source).with(routingKey);
        Binding retry = BindingBuilder.bind(wait).to(retryEvents).with(queueName);
        return List.of(queue, wait, dlq, main, retry);
    }
}
