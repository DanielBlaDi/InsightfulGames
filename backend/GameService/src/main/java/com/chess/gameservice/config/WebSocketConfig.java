package com.chess.gameservice.config;

import com.chess.gameservice.websocket.GameWebSocketHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    /** Ruta interna del contrato (12.4.1). La pública, /ws/games/{id}, la atiende el gateway web. */
    public static final String GAME_SOCKET_PATH = "/internal/single-player/ws/games/*";

    private final GameWebSocketHandler handler;

    public WebSocketConfig(GameWebSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        // Solo es alcanzable por el gateway, que ya valida Origin y sesión (contrato, 12.7).
        registry.addHandler(handler, GAME_SOCKET_PATH).setAllowedOrigins("*");
    }
}
