package com.chess.gameservice.config;

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

/**
 * Topología de RabbitMQ que usa Single Player (contrato, 19.3). Las declaraciones son idempotentes
 * y usan los mismos argumentos que los demás consumidores de game.events y retry.events.
 */
@Configuration
public class RabbitTopology {

    public static final String GAME_EVENTS = "game.events";
    public static final String RETRY_EVENTS = "retry.events";
    public static final String GAME_FINISHED = "game.finished";

    public static final String GAME_FINISHED_QUEUE = "single-player.game-finished";
    public static final String WAIT_QUEUE = GAME_FINISHED_QUEUE + ".wait";
    public static final String DLQ = GAME_FINISHED_QUEUE + ".dlq";

    /** Encabezado que cuenta los reenvíos (19.4): un intento inicial y cinco reintentos. */
    public static final String RETRY_COUNT_HEADER = "x-retry-count";
    public static final int MAX_RETRIES = 5;
    public static final int RETRY_DELAY_MS = 5000;

    @Bean
    public Declarables singlePlayerTopology() {
        TopicExchange gameEvents = ExchangeBuilder.topicExchange(GAME_EVENTS).durable(true).build();
        DirectExchange retryEvents = ExchangeBuilder.directExchange(RETRY_EVENTS).durable(true).build();

        Queue queue = QueueBuilder.durable(GAME_FINISHED_QUEUE).build();
        Queue wait = QueueBuilder.durable(WAIT_QUEUE)
                .ttl(RETRY_DELAY_MS)
                .deadLetterExchange("")
                .deadLetterRoutingKey(GAME_FINISHED_QUEUE)
                .build();
        Queue dlq = QueueBuilder.durable(DLQ).build();

        Binding main = BindingBuilder.bind(queue).to(gameEvents).with(GAME_FINISHED);
        Binding retry = BindingBuilder.bind(wait).to(retryEvents).with(GAME_FINISHED_QUEUE);
        return new Declarables(gameEvents, retryEvents, queue, wait, dlq, main, retry);
    }
}
