package com.chess.gameservice.websocket;

import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.GameState;
import com.chess.gameservice.service.SinglePlayerService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;

/**
 * WebSocket /internal/single-player/ws/games/{id} (contrato, 12.4.1). El gateway web valida Origin y la
 * sesión, comprueba que el usuario participe y reenvía el usuario en la cabecera X-User-Id. Solo se
 * aceptan participantes.
 *
 * <p>Este hub es solo de salida: registra la sesión, envía el state inicial y deja que {@code publish}
 * (del gateway) y game.finished envíen el resto. Los mensajes del cliente (move, resign) los atiende el
 * gateway, que opera en Game Logic y Botcito, y responde él mismo move_rejected o error al cliente. Si
 * un mensaje llegara aquí directamente, se ignora.
 */
@Component
public class GameWebSocketHandler extends TextWebSocketHandler {

    /** Códigos de cierre del contrato. */
    static final CloseStatus UNAUTHORIZED = new CloseStatus(4401, "Sesion invalida o vencida");
    static final CloseStatus GAME_NOT_FOUND = new CloseStatus(4404, "Partida inexistente o ajena");

    private static final Logger log = LoggerFactory.getLogger(GameWebSocketHandler.class);
    private static final String GAME_ATTR = "gameId";

    private final SinglePlayerService service;
    private final GameChannels channels;

    public GameWebSocketHandler(SinglePlayerService service, GameChannels channels) {
        this.service = service;
        this.channels = channels;
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

        session.getAttributes().put(GAME_ATTR, gameId);
        channels.register(gameId, session);

        // Al conectarse se envía un state completo, sin lastMove
        channels.send(session, WsMessage.state(state, null));
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        // Las acciones del cliente las atiende el gateway: aquí no se hace nada con ellas.
        log.debug("Mensaje del cliente ignorado en el hub (sesión {})", session.getId());
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        String gameId = (String) session.getAttributes().get(GAME_ATTR);
        if (gameId != null) {
            channels.unregister(gameId, session);
        }
    }

    /** La ruta es .../ws/games/{id}: el ID es el último segmento. */
    private static String gameIdFrom(WebSocketSession session) {
        String path = session.getUri() == null ? "" : session.getUri().getPath();
        return path.substring(path.lastIndexOf('/') + 1);
    }
}
