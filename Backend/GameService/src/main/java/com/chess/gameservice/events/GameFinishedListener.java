package com.chess.gameservice.events;

import com.chess.gameservice.config.RabbitTopology;
import com.chess.gameservice.service.SinglePlayerService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

import java.io.IOException;

import static com.chess.gameservice.config.RabbitTopology.MAX_RETRIES;
import static com.chess.gameservice.config.RabbitTopology.RETRY_COUNT_HEADER;

/**
 * Consumidor de single-player.game-finished (contrato, 19.6.2). Filtra mode local o vs_bot, relee
 * la partida y envía state y game_over a las sesiones abiertas.
 *
 * <p>El mensaje se confirma (ack) al terminar el método: después de procesarlo, o después de
 * reenviarlo a retry.events o a la .dlq. Si ese reenvío falla, la excepción hace que el mensaje
 * se rechace con requeue.
 */
@Component
public class GameFinishedListener {

    private static final Logger log = LoggerFactory.getLogger(GameFinishedListener.class);

    private final SinglePlayerService service;
    private final RabbitTemplate rabbit;
    private final ObjectMapper mapper;

    public GameFinishedListener(SinglePlayerService service, RabbitTemplate rabbit, ObjectMapper mapper) {
        this.service = service;
        this.rabbit = rabbit;
        this.mapper = mapper;
    }

    @RabbitListener(queues = RabbitTopology.GAME_FINISHED_QUEUE)
    public void onGameFinished(Message message) {
        String gameId;
        String mode;
        try {
            JsonNode event = mapper.readTree(message.getBody());
            gameId = text(event, "gameId");
            mode = text(event, "mode");
            if (gameId == null || mode == null) {
                throw new IOException("faltan gameId o mode");
            }
        } catch (IOException | RuntimeException e) {
            log.warn("Evento game.finished inválido: {}. Se envía a la DLQ", e.getMessage());
            rabbit.send("", RabbitTopology.DLQ, message);
            return;
        }

        if (!SinglePlayerService.LOCAL.equals(mode) && !SinglePlayerService.VS_BOT.equals(mode)) {
            return; // multiplayer: lo atiende Multiplayer
        }

        try {
            service.notifyFinished(gameId);
        } catch (RuntimeException e) {
            log.warn("Falló la notificación de fin de la partida {} (intento {}): {}",
                    gameId, retryCount(message) + 1, e.toString());
            retryOrDeadLetter(message);
        }
    }

    private void retryOrDeadLetter(Message message) {
        int count = retryCount(message);
        if (count >= MAX_RETRIES) {
            rabbit.send("", RabbitTopology.DLQ, message);
            return;
        }
        Message retry = MessageBuilder.fromMessage(message).setHeader(RETRY_COUNT_HEADER, count + 1).build();
        rabbit.send(RabbitTopology.RETRY_EVENTS, RabbitTopology.GAME_FINISHED_QUEUE, retry);
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

    private static String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        return value != null && value.isTextual() && !value.asText().isBlank() ? value.asText() : null;
    }
}
