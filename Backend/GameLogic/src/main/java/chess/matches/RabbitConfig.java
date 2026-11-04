package chess.matches;

import org.springframework.amqp.core.ExchangeBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** El productor declara su exchange (contrato, 19.3): game.events, topic y durable. */
@Configuration
public class RabbitConfig{
    public static final String GAME_EVENTS = "game.events";
    public static final String GAME_FINISHED = "game.finished";

    @Bean
    public TopicExchange gameEventsExchange(){
        return ExchangeBuilder.topicExchange(GAME_EVENTS).durable(true).build();
    }
}
