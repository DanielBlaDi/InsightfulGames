package com.prototipo.auth.events;

import org.springframework.amqp.core.ExchangeBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Exchange de la sección 17 donde Auth publica. Las colas las declara cada consumidor
 * (Profile/Stats declara profile.user-registered). Mismos argumentos que en los demás servicios.
 */
@Configuration
public class UserEventsTopology {

    public static final String USER_EVENTS = "user.events";
    public static final String USER_REGISTERED = "user.registered";

    @Bean
    public TopicExchange userEventsExchange() {
        return ExchangeBuilder.topicExchange(USER_EVENTS).durable(true).build();
    }
}
