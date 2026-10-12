package com.chess.gameservice.websocket;

import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.GameState;
import com.chess.gameservice.service.SinglePlayerService;
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

/**
 * WebSocket /ws/games/{id} (contrato, sección 5). El API Gateway valida el token al abrir
 * la conexión y reenvía el ID del usuario en la cabecera X-User-Id.
 */
@Component
public class GameWebSocketHandler extends TextWebSocketHandler {

    /** Códigos de cierre del contrato. */
    static final CloseStatus UNAUTHORIZED = new CloseStatus(4401, "Token invalido o vencido");
    static final CloseStatus GAME_NOT_FOUND = new CloseStatus(4404, "Partida inexistente o ajena");

    private static final Logger log = LoggerFactory.getLogger(GameWebSocketHandler.class);
    private static final String USER_ATTR = "userId";
    private static final String GAME_ATTR = "gameId";

    private final SinglePlayerService service;
    private final GameChannels channels;
    private final ObjectMapper mapper;

    public GameWebSocketHandler(SinglePlayerService service, GameChannels channels, ObjectMapper mapper) {
        this.service = service;
        this.channels = channels;
        this.mapper = mapper;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws IOException {
        String userId = session.getHandshakeHeaders().getFirst("X-User-Id");
        String gameId = gameIdFrom(session);

        if (userId == null || userId.isBlank()) {
            session.close(UNAUTHORIZED);
            return;
        }

        GameState state;
        try {
            state = service.getGame(userId, gameId);
        } catch (ApiException e) {
            session.close(e.status().value() == 404 ? GAME_NOT_FOUND : CloseStatus.SERVER_ERROR);
            return;
        }

        session.getAttributes().put(USER_ATTR, userId);
        session.getAttributes().put(GAME_ATTR, gameId);
        channels.register(gameId, session);

        // Al conectarse se envía un state completo, sin lastMove
        channels.send(session, WsMessage.state(state, null));
        service.resumeBotIfNeeded(state);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        String userId = (String) session.getAttributes().get(USER_ATTR);
        String gameId = (String) session.getAttributes().get(GAME_ATTR);
        if (userId == null || gameId == null) {
            return;
        }

        ClientMessage request;
        try {
            request = mapper.readValue(message.getPayload(), ClientMessage.class);
        } catch (JsonProcessingException e) {
            channels.send(session, WsMessage.error("VALIDATION_ERROR", "El mensaje no es un JSON válido"));
            return;
        }
        if (request == null || request.type() == null) {
            channels.send(session, WsMessage.error("VALIDATION_ERROR", "Falta el campo type"));
            return;
        }

        try {
            switch (request.type()) {
                case "move" -> service.handleMove(userId, gameId, request.uci());
                case "resign" -> service.resign(userId, gameId, request.side());
                default -> channels.send(session,
                        WsMessage.error("VALIDATION_ERROR", "Tipo de mensaje desconocido: " + request.type()));
            }
        } catch (ApiException e) {
            // 400 y 422 son jugadas o rendiciones rechazadas; lo demás (404, 502...) es un error
            boolean rejected = e.status().value() == 400 || e.status().value() == 422;
            channels.send(session, rejected
                    ? WsMessage.moveRejected(e.code(), e.getMessage())
                    : WsMessage.error(e.code(), e.getMessage()));
        } catch (RuntimeException e) {
            log.error("Error inesperado en la partida {}", gameId, e);
            channels.send(session, WsMessage.error("INTERNAL_ERROR", "Error interno del servidor"));
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        String gameId = (String) session.getAttributes().get(GAME_ATTR);
        if (gameId != null) {
            channels.unregister(gameId, session);
        }
    }

    /** La ruta es /ws/games/{id}: el ID es el último segmento. */
    private static String gameIdFrom(WebSocketSession session) {
        String path = session.getUri() == null ? "" : session.getUri().getPath();
        return path.substring(path.lastIndexOf('/') + 1);
    }
}
