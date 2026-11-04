package chess.matches;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.amqp.AmqpConnectException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

import tools.jackson.databind.ObjectMapper;

/** Publicar nunca cambia la respuesta HTTP (contrato, 11.4.10), y el cuerpo lleva eventId (19.6.2). */
class RabbitPublisherTest{

    static final MatchFinishedMessage EVENT = new MatchFinishedMessage("11111111-2222-4333-8444-555555555555", "game.finished",
        "2026-11-03T15:20:00Z", "3f2b1c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d", null, "local",
        List.of(new Participant("aaaaaaaa-1111-4111-8111-111111111111", "white")), null, "account_deleted", "2026-11-03T15:20:00Z");

    @Test
    void brokerFailureDoesNotPropagate(){
        RabbitTemplate template = mock(RabbitTemplate.class);
        doThrow(new AmqpConnectException(new java.net.ConnectException("ACCESS_REFUSED")))
            .when(template).send(any(String.class), any(String.class), any(Message.class), any(CorrelationData.class));

        RabbitPublisher publisher = new RabbitPublisher(new ObjectMapper(), template);

        assertThatCode(() -> publisher.publishMatchFinishedMessage(EVENT)).doesNotThrowAnyException();
    }

    @Test
    void publishesToGameEventsWithEventIdInTheBodyAndAsMessageId(){
        RabbitTemplate template = mock(RabbitTemplate.class);
        new RabbitPublisher(new ObjectMapper(), template).publishMatchFinishedMessage(EVENT);

        ArgumentCaptor<Message> message = ArgumentCaptor.forClass(Message.class);
        verify(template).send(eq("game.events"), eq("game.finished"), message.capture(), any(CorrelationData.class));
        String body = new String(message.getValue().getBody(), java.nio.charset.StandardCharsets.UTF_8);
        org.assertj.core.api.Assertions.assertThat(body).contains("\"eventId\":\"" + EVENT.eventId() + "\"").contains("\"eventType\":\"game.finished\"");
        org.assertj.core.api.Assertions.assertThat(message.getValue().getMessageProperties().getMessageId()).isEqualTo(EVENT.eventId());
    }
}
