package com.chess.gameservice.websocket;

import com.chess.gameservice.protocol.ClientMessage;
import com.chess.gameservice.protocol.ServerMessage;
import com.chess.gameservice.session.GameCoordinator;
import com.chess.gameservice.session.GameMode;
import com.chess.gameservice.session.GameSession;
import com.chess.gameservice.session.SessionManager;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.function.Consumer;

@Component
public class GameWebSocketHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(GameWebSocketHandler.class);
    private static final String GAME_ID = "gameId";

    private final ObjectMapper mapper;
    private final GameCoordinator coordinator;
    private final SessionManager sessions;

    public GameWebSocketHandler(ObjectMapper mapper, GameCoordinator coordinator, SessionManager sessions) {
        this.mapper = mapper;
        this.coordinator = coordinator;
        this.sessions = sessions;
    }

    @Override
    protected void handleTextMessage(WebSocketSession ws, TextMessage text) {
        ClientMessage msg;
        try {
            msg = mapper.readValue(text.getPayload(), ClientMessage.class);
        } catch (JsonProcessingException e) {
            send(ws, ServerMessage.error("JSON inválido"));
            return;
        }

        String type = msg.type() == null ? "" : msg.type();
        switch (type) {
            case "create_game" -> createGame(ws, msg);
            case "move" -> withSession(ws, s -> coordinator.handleMove(s, msg.move()));
            case "resign" -> withSession(ws, coordinator::resign);
            default -> send(ws, ServerMessage.error("Tipo de mensaje desconocido: " + type));
        }
    }

    private void createGame(WebSocketSession ws, ClientMessage msg) {
        GameMode mode;
        try {
            mode = GameMode.valueOf(String.valueOf(msg.mode()).toUpperCase());
        } catch (IllegalArgumentException e) {
            send(ws, ServerMessage.error("mode debe ser LOCAL o BOT"));
            return;
        }
        // RF-13: dificultad de 1 a 20
        int difficulty = msg.difficulty() == null ? 10 : Math.max(1, Math.min(20, msg.difficulty()));
        String color = "BLACK".equalsIgnoreCase(msg.color()) ? "BLACK" : "WHITE";

        String previous = (String) ws.getAttributes().get(GAME_ID);
        if (previous != null) {
            coordinator.close(previous);
        }

        try {
            GameSession session = coordinator.createGame(mode, difficulty, color, resolveUserId(ws, msg),
                    out -> send(ws, out));
            ws.getAttributes().put(GAME_ID, session.id());
        } catch (RuntimeException e) {
            log.error("No se pudo crear la partida", e);
            send(ws, ServerMessage.error("No se pudo crear la partida en el servicio de lógica"));
        }
    }

    /**
     * El API Gateway debe enviar el header X-User-Id (sacado del JWT).
     * Si no llega, se usa el playerId del mensaje y, en último caso, el ID de invitado.
     */
    private long resolveUserId(WebSocketSession ws, ClientMessage msg) {
        String header = ws.getHandshakeHeaders().getFirst("X-User-Id");
        if (header != null) {
            try {
                return Long.parseLong(header.trim());
            } catch (NumberFormatException ignored) {
                // se usa el valor del mensaje
            }
        }
        return msg.playerId() != null ? msg.playerId() : GameCoordinator.GUEST_PLAYER_ID;
    }

    private void withSession(WebSocketSession ws, Consumer<GameSession> action) {
        String id = (String) ws.getAttributes().get(GAME_ID);
        sessions.find(id).ifPresentOrElse(
                action,
                () -> send(ws, ServerMessage.error("No hay partida activa. Envía create_game primero.")));
    }

    @Override
    public void afterConnectionClosed(WebSocketSession ws, CloseStatus status) {
        String id = (String) ws.getAttributes().get(GAME_ID);
        if (id != null) {
            coordinator.close(id);
        }
    }

    /** WebSocketSession no admite envíos concurrentes, por eso se sincroniza. */
    private void send(WebSocketSession ws, ServerMessage msg) {
        synchronized (ws) {
            try {
                if (ws.isOpen()) {
                    ws.sendMessage(new TextMessage(mapper.writeValueAsString(msg)));
                }
            } catch (IOException e) {
                log.warn("No se pudo enviar mensaje a {}: {}", ws.getId(), e.getMessage());
            }
        }
    }
}
