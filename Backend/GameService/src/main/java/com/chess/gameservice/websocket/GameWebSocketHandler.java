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
 * WebSocket /internal/single-player/ws/games/{id} (contrato, 12.4.1). El gateway web valida Origin
 * y la sesión, y reenvía el usuario en la cabecera X-User-Id. Solo se aceptan participantes.
 *
 * <p>Clasificación de las respuestas a un mensaje del cliente:
 * <ul>
 *   <li>move_rejected: la acción no se aceptó (400 VALIDATION_ERROR, 409 VERSION_CONFLICT,
 *   409 GAME_NOT_IN_PROGRESS, 422 INVALID_MOVE, NOT_YOUR_TURN, GAME_FINISHED, CLOCK_EXPIRED...).</li>
 *   <li>error: fallo ajeno a la jugada que no cambia la partida (503 SERVICES_UNAVAILABLE,
 *   ENGINE_BUSY, 504 ENGINE_TIMEOUT, 404, INTERNAL_ERROR...).</li>
 * </ul>
 */
@Component
public class GameWebSocketHandler extends TextWebSocketHandler {

    /** Códigos de cierre del contrato. */
    static final CloseStatus UNAUTHORIZED = new CloseStatus(4401, "Sesion invalida o vencida");
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
            state = service.getParticipantGame(userId, gameId);
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
            channels.send(session, WsMessage.moveRejected("VALIDATION_ERROR", "El mensaje no es un JSON válido"));
            return;
        }
        if (request == null || request.type() == null) {
            channels.send(session, WsMessage.moveRejected("VALIDATION_ERROR", "Falta el campo type"));
            return;
        }

        try {
            switch (request.type()) {
                case "move" -> service.handleMove(userId, gameId, request.uci(), request.expectedVersion());
                case "resign" -> service.resign(userId, gameId, request.side());
                default -> channels.send(session,
                        WsMessage.moveRejected("VALIDATION_ERROR", "Tipo de mensaje desconocido: " + request.type()));
            }
        } catch (ApiException e) {
            channels.send(session, isRejection(e)
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

    /** 400, 409 y 422 son acciones no aceptadas; el resto (404, 5xx) son fallos ajenos a la jugada. */
    static boolean isRejection(ApiException e) {
        int status = e.status().value();
        return status == 400 || status == 409 || status == 422;
    }

    /** La ruta es .../ws/games/{id}: el ID es el último segmento. */
    private static String gameIdFrom(WebSocketSession session) {
        String path = session.getUri() == null ? "" : session.getUri().getPath();
        return path.substring(path.lastIndexOf('/') + 1);
    }
}
