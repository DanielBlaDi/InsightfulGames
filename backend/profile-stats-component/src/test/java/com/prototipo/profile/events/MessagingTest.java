package com.prototipo.profile.events;

import com.prototipo.profile.config.RabbitTopology;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import tools.jackson.databind.json.JsonMapper;

import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

/** Reintentos, DLQ, validación de mensajes y topología, sin broker. */
class MessagingTest {

    private static final String QUEUE = RabbitTopology.GAME_FINISHED_QUEUE;

    private final RabbitTemplate rabbit = mock(RabbitTemplate.class);
    private final RetryPublisher retries = new RetryPublisher(rabbit);
    private final EventParser parser = new EventParser(JsonMapper.builder().build());

    private static Message message(Object retryCount) {
        MessageProperties props = new MessageProperties();
        if (retryCount != null) {
            props.setHeader(RabbitTopology.RETRY_COUNT_HEADER, retryCount);
        }
        return new Message("{}".getBytes(StandardCharsets.UTF_8), props);
    }

    private Message sentToRetry() {
        ArgumentCaptor<Message> captor = ArgumentCaptor.forClass(Message.class);
        verify(rabbit).send(eq("retry.events"), eq(QUEUE), captor.capture());
        return captor.getValue();
    }

    @Test
    void firstFailureGoesToRetryWithCountOne() {
        retries.retryOrDeadLetter(message(null), QUEUE);

        assertThat(RetryPublisher.retryCount(sentToRetry())).isEqualTo(1);
    }

    @Test
    void retryCountGrowsUntilFive() {
        retries.retryOrDeadLetter(message(4), QUEUE);

        assertThat(RetryPublisher.retryCount(sentToRetry())).isEqualTo(5);
    }

    @Test
    void failureAtCountFiveGoesToTheDlq() {
        Message failed = message(5);

        retries.retryOrDeadLetter(failed, QUEUE);

        verify(rabbit).send("", "profile.game-finished.dlq", failed);
        verify(rabbit, never()).send(eq("retry.events"), anyString(), any(Message.class));
    }

    @Test
    void retryCountAcceptsNumbersAndText() {
        assertThat(RetryPublisher.retryCount(message(3L))).isEqualTo(3);
        assertThat(RetryPublisher.retryCount(message("2"))).isEqualTo(2);
        assertThat(RetryPublisher.retryCount(message("basura"))).isZero();
    }

    @Test
    void listenerRetriesProcessingFailuresAndDeadLettersInvalidMessages() {
        EventListeners listeners = new EventListeners(parser, null, retries);

        listeners.handle(message(null), QUEUE, () -> { throw new IllegalStateException("base caída"); });
        assertThat(RetryPublisher.retryCount(sentToRetry())).isEqualTo(1);

        Message invalid = message(null);
        listeners.handle(invalid, QUEUE, () -> { throw new InvalidEventException("sin eventId"); });
        verify(rabbit).send("", "profile.game-finished.dlq", invalid);
    }

    @Test
    void listenerDoesNothingElseOnSuccess() {
        new EventListeners(parser, null, retries).handle(message(null), QUEUE, () -> { });

        verifyNoInteractions(rabbit);
    }

    @Test
    void parserRejectsMessagesOutsideTheContract() {
        String ok = "{\"eventId\":\"11111111-1111-4111-8111-111111111111\",\"eventType\":\"user.registered\","
                + "\"userId\":\"22222222-2222-4222-8222-222222222222\",\"username\":\"ana\"}";
        assertThat(parser.userRegistered(ok.getBytes(StandardCharsets.UTF_8)).username()).isEqualTo("ana");

        for (String bad : new String[] {
                "no es json",
                ok.replace("user.registered", "game.finished"),
                ok.replace("11111111-1111-4111-8111-111111111111", "abc"),
                ok.replace("\"ana\"", "\"un-nombre-demasiado-largo\"") }) {
            assertThatThrownBy(() -> parser.userRegistered(bad.getBytes(StandardCharsets.UTF_8)))
                    .isInstanceOf(InvalidEventException.class);
        }

        String badColor = "{\"eventId\":\"11111111-1111-4111-8111-111111111111\",\"eventType\":\"game.finished\","
                + "\"mode\":\"multiplayer\",\"participants\":[{\"userId\":\"22222222-2222-4222-8222-222222222222\","
                + "\"color\":\"red\"}],\"result\":\"white\"}";
        assertThatThrownBy(() -> parser.gameFinished(badColor.getBytes(StandardCharsets.UTF_8)))
                .isInstanceOf(InvalidEventException.class);
    }

    @Test
    void waitQueuesReturnMessagesToTheirQueueAfterFiveSeconds() {
        Declarables declarables = new RabbitTopology().profileTopology();
        Queue wait = declarables.getDeclarablesByType(Queue.class).stream()
                .filter(q -> q.getName().equals("profile.game-finished.wait"))
                .findFirst().orElseThrow();

        assertThat(wait.getArguments())
                .containsEntry("x-message-ttl", 5000)
                .containsEntry("x-dead-letter-exchange", "")
                .containsEntry("x-dead-letter-routing-key", QUEUE);
        assertThat(declarables.getDeclarablesByType(Queue.class)).extracting(Queue::getName)
                .contains("profile.user-registered", "profile.user-registered.dlq",
                        "profile.game-finished", "profile.game-finished.dlq");
    }
}
