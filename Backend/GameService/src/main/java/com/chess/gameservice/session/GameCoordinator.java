package com.chess.gameservice.session;

import com.chess.gameservice.logic.GameLogic;
import com.chess.gameservice.logic.MoveResult;
import com.chess.gameservice.logic.MoveResult.Outcome;
import com.chess.gameservice.modes.BotMode;
import com.chess.gameservice.protocol.ServerMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.function.Consumer;

/**
 * Orquesta una partida: valida y guarda cada jugada en Game Logic (tarea 6),
 * actualiza la sesión, avisa al cliente y, en modo BOT, pide la respuesta a Botcito.
 * El modo LOCAL no necesita lógica extra: los turnos se alternan según el FEN.
 */
@Service
public class GameCoordinator {

    /** ID de jugador que se registra en Game Logic para las jugadas de Botcito. */
    public static final long BOT_PLAYER_ID = 0L;
    /** ID de jugador cuando el cliente no se identificó (pruebas sin login). */
    public static final long GUEST_PLAYER_ID = -1L;

    private static final Logger log = LoggerFactory.getLogger(GameCoordinator.class);

    private final SessionManager sessions;
    private final GameLogic logic;
    private final BotMode botMode;

    public GameCoordinator(SessionManager sessions, GameLogic logic, BotMode botMode) {
        this.sessions = sessions;
        this.logic = logic;
        this.botMode = botMode;
    }

    /** Lanza RuntimeException si Game Logic no puede crear la partida. */
    public GameSession createGame(GameMode mode, int difficulty, String humanColor, long userId,
                                  Consumer<ServerMessage> out) {
        long white = userId;
        long black = userId; // LOCAL: los dos jugadores comparten el dispositivo y la cuenta
        if (mode == GameMode.BOT) {
            if ("WHITE".equals(humanColor)) {
                black = BOT_PLAYER_ID;
            } else {
                white = BOT_PLAYER_ID;
            }
        }

        String matchId = logic.createMatch(white, black);
        GameSession s = sessions.create(matchId, mode, difficulty, humanColor, white, black, out);
        synchronized (s) {
            s.send(ServerMessage.created(s.id(), mode.name(), s.fen(), s.turn()));
            // Si el humano juega con negras, el bot abre la partida.
            if (mode == GameMode.BOT && "BLACK".equals(humanColor)) {
                botMode.requestMove(s, this::applyBotMove);
            }
        }
        return s;
    }

    public void handleMove(GameSession s, String uciMove) {
        synchronized (s) {
            if (s.isFinished()) {
                s.send(ServerMessage.error("La partida ya terminó"));
                return;
            }
            if (s.mode() == GameMode.BOT && !s.turn().equals(s.humanColor())) {
                s.send(ServerMessage.error("Es el turno de Botcito"));
                return;
            }
            MoveResult result = applyOrNull(s, uciMove);
            if (result == null) {
                return;
            }
            if (!result.legal()) {
                s.send(ServerMessage.error(result.reason()));
                return;
            }
            s.recordMove(uciMove, result);
            s.send(ServerMessage.state(s.id(), s.fen(), s.turn(), uciMove));

            if (result.finished()) {
                finish(s, result.outcome(), result.reason());
            } else if (s.mode() == GameMode.BOT) {
                botMode.requestMove(s, this::applyBotMove);
            }
        }
    }

    /** Se invoca desde otro hilo cuando Botcito responde. */
    private void applyBotMove(GameSession s, String uciMove) {
        synchronized (s) {
            if (s.isFinished()) {
                return; // el jugador abandonó o se desconectó mientras el bot pensaba
            }
            MoveResult result = applyOrNull(s, uciMove);
            if (result == null) {
                return;
            }
            if (!result.legal()) {
                s.send(ServerMessage.error("Botcito devolvió una jugada ilegal: " + uciMove));
                return;
            }
            s.recordMove(uciMove, result);
            s.send(ServerMessage.state(s.id(), s.fen(), s.turn(), uciMove));
            if (result.finished()) {
                finish(s, result.outcome(), result.reason());
            }
        }
    }

    /** RF-22: abandonar. En LOCAL abandona quien tiene el turno; en BOT, el humano. */
    public void resign(GameSession s) {
        synchronized (s) {
            if (s.isFinished()) {
                return;
            }
            String loser = s.mode() == GameMode.BOT ? s.humanColor() : s.turn();
            Outcome outcome = loser.equals("WHITE") ? Outcome.BLACK_WINS : Outcome.WHITE_WINS;
            finish(s, outcome, "RESIGNATION");
        }
    }

    /** Se llama al cerrarse el WebSocket: la sesión en memoria se descarta. */
    public void close(String gameId) {
        sessions.remove(gameId).ifPresent(s -> {
            synchronized (s) {
                s.finish();
            }
        });
    }

    /** Llama a Game Logic; si el servicio falla avisa al cliente y devuelve null. */
    private MoveResult applyOrNull(GameSession s, String uciMove) {
        try {
            return logic.applyMove(s.id(), s.fen(), uciMove, s.currentPlayerId());
        } catch (RuntimeException e) {
            log.error("Falló la llamada a Game Logic para la partida {}", s.id(), e);
            s.send(ServerMessage.error("El servicio de lógica de juego no respondió, intenta de nuevo"));
            return null;
        }
    }

    private void finish(GameSession s, Outcome outcome, String reason) {
        s.finish();
        s.send(ServerMessage.gameOver(s.id(), outcome.name(), reason));
        try {
            logic.finishMatch(s.id(), outcome, reason); // guarda el resultado en MongoDB
        } catch (RuntimeException e) {
            log.error("No se pudo guardar el resultado de la partida {}", s.id(), e);
        }
    }
}
