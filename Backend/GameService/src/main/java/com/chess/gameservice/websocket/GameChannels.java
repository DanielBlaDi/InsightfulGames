package com.chess.gameservice.websocket;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

import java.io.IOException;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArraySet;

/** Sesiones WebSocket conectadas a cada partida, para enviarles los cambios. */
@Component
public class GameChannels {

    private static final Logger log = LoggerFactory.getLogger(GameChannels.class);

    private final ObjectMapper mapper;
    private final ConcurrentHashMap<String, Set<WebSocketSession>> sessions = new ConcurrentHashMap<>();

    public GameChannels(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void register(String gameId, WebSocketSession session) {
        sessions.computeIfAbsent(gameId, id -> new CopyOnWriteArraySet<>()).add(session);
    }

    public void unregister(String gameId, WebSocketSession session) {
        Set<WebSocketSession> set = sessions.get(gameId);
        if (set != null) {
            set.remove(session);
            if (set.isEmpty()) {
                sessions.remove(gameId, set);
            }
        }
    }

    public void broadcast(String gameId, WsMessage message) {
        Set<WebSocketSession> set = sessions.get(gameId);
        if (set == null) {
            return;
        }
        for (WebSocketSession session : set) {
            send(session, message);
        }
    }

    public void send(WebSocketSession session, WsMessage message) {
        try {
            TextMessage text = new TextMessage(mapper.writeValueAsString(message));
            // WebSocketSession no admite envíos simultáneos desde varios hilos
            synchronized (session) {
                if (session.isOpen()) {
                    session.sendMessage(text);
                }
            }
        } catch (JsonProcessingException e) {
            log.error("No se pudo serializar el mensaje {}", message.type(), e);
        } catch (IOException e) {
            log.warn("No se pudo enviar el mensaje {} a la sesión {}", message.type(), session.getId());
        }
    }
}
