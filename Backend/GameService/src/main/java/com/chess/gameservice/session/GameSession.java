package com.chess.gameservice.session;

import com.chess.gameservice.logic.GameLogic;
import com.chess.gameservice.logic.MoveResult;
import com.chess.gameservice.protocol.ServerMessage;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

/** Estado de una partida. Quien la modifique debe hacerlo con synchronized(session). */
public class GameSession {

    private final String id; // ID de la partida en Game Logic (el mismo que se guarda en Mongo)
    private final GameMode mode;
    private final int difficulty;
    private final String humanColor; // solo relevante en modo BOT
    private final long whitePlayerId;
    private final long blackPlayerId;
    private final Instant createdAt = Instant.now();
    private final List<String> moves = new ArrayList<>();
    private final Consumer<ServerMessage> out; // canal hacia el cliente

    private String fen = GameLogic.START_FEN;
    private String turn = "WHITE";
    private boolean finished;

    public GameSession(String id, GameMode mode, int difficulty, String humanColor,
                       long whitePlayerId, long blackPlayerId, Consumer<ServerMessage> out) {
        this.id = id;
        this.mode = mode;
        this.difficulty = difficulty;
        this.humanColor = humanColor;
        this.whitePlayerId = whitePlayerId;
        this.blackPlayerId = blackPlayerId;
        this.out = out;
    }

    public void send(ServerMessage message) {
        out.accept(message);
    }

    public void recordMove(String uciMove, MoveResult result) {
        moves.add(uciMove);
        fen = result.fen();
        turn = result.turn();
        finished = result.finished();
    }

    public void finish() {
        finished = true;
    }

    /** ID del jugador al que le toca mover (el bot tiene el ID 0). */
    public long currentPlayerId() {
        return "WHITE".equals(turn) ? whitePlayerId : blackPlayerId;
    }

    public String id() { return id; }
    public GameMode mode() { return mode; }
    public int difficulty() { return difficulty; }
    public String humanColor() { return humanColor; }
    public Instant createdAt() { return createdAt; }
    public List<String> moves() { return List.copyOf(moves); }
    public String fen() { return fen; }
    public String turn() { return turn; }
    public boolean isFinished() { return finished; }
}
