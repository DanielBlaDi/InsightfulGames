package com.chess.gameservice.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.service.SinglePlayerService;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Filtro, DLQ y reintentos del consumidor de single-player.game-finished (19.4 y 19.6.2). */
class GameFinishedListenerTest {

    static final String GAME = "3f2b1c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d";

    private SinglePlayerService service;
    private RabbitTemplate rabbit;
    private GameFinishedListener listener;

    @BeforeEach
    void setUp() {
        service = mock(SinglePlayerService.class);
        rabbit = mock(RabbitTemplate.class);
        listener = new GameFinishedListener(service, rabbit, new ObjectMapper());
    }

    private static Message message(String json, Integer retries) {
        MessageProperties props = new MessageProperties();
        if (retries != null) {
            props.setHeader("x-retry-count", retries);
        }
        return new Message(json.getBytes(StandardCharsets.UTF_8), props);
    }

    private static String event(String mode) {
        return "{\"eventType\":\"game.finished\",\"gameId\":\"" + GAME + "\",\"mode\":\"" + mode + "\"}";
    }

    @Test
    void localAndBotGamesAreNotified() {
        listener.onGameFinished(message(event("local"), null));
        listener.onGameFinished(message(event("vs_bot"), null));
        verify(service, org.mockito.Mockito.times(2)).notifyFinished(GAME);
        verifyNoInteractions(rabbit);
    }

    @Test
    void multiplayerGamesAreIgnored() {
        listener.onGameFinished(message(event("multiplayer"), null));
        verifyNoInteractions(service, rabbit);
    }

    @Test
    void invalidMessagesGoStraightToTheDlq() {
        for (String json : new String[]{"no es json", "{\"mode\":\"local\"}", "{\"gameId\":\"" + GAME + "\"}"}) {
            listener.onGameFinished(message(json, null));
        }
        verify(rabbit, org.mockito.Mockito.times(3)).send(eq(""), eq("single-player.game-finished.dlq"), any(Message.class));
        verifyNoInteractions(service);
    }

    @Test
    void failuresAreRetriedWithAnIncreasedCount() {
        doThrow(ApiException.unavailable("caído")).when(service).notifyFinished(GAME);

        listener.onGameFinished(message(event("local"), 2));

        ArgumentCaptor<Message> retry = ArgumentCaptor.forClass(Message.class);
        verify(rabbit).send(eq("retry.events"), eq("single-player.game-finished"), retry.capture());
        assertEquals(3, (Integer) retry.getValue().getMessageProperties().getHeader("x-retry-count"));
    }

    @Test
    void afterFiveRetriesTheMessageGoesToTheDlq() {
        doThrow(ApiException.unavailable("caído")).when(service).notifyFinished(GAME);

        listener.onGameFinished(message(event("vs_bot"), 5));

        verify(rabbit).send(eq(""), eq("single-player.game-finished.dlq"), any(Message.class));
        verify(rabbit, never()).send(eq("retry.events"), anyString(), any(Message.class));
    }
}
