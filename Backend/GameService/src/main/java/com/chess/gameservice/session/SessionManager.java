package com.chess.gameservice.session;

import com.chess.gameservice.protocol.ServerMessage;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;

@Component
public class SessionManager {

    private final Map<String, GameSession> sessions = new ConcurrentHashMap<>();

    public GameSession create(String matchId, GameMode mode, int difficulty, String humanColor,
                              long whitePlayerId, long blackPlayerId, Consumer<ServerMessage> out) {
        GameSession session = new GameSession(matchId, mode, difficulty, humanColor, whitePlayerId, blackPlayerId, out);
        sessions.put(session.id(), session);
        return session;
    }

    public Optional<GameSession> find(String id) {
        return id == null ? Optional.empty() : Optional.ofNullable(sessions.get(id));
    }

    public Optional<GameSession> remove(String id) {
        return id == null ? Optional.empty() : Optional.ofNullable(sessions.remove(id));
    }
}
