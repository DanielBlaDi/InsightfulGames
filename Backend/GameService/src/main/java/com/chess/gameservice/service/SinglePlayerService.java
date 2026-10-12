package com.chess.gameservice.service;

import com.chess.gameservice.client.BotcitoClient;
import com.chess.gameservice.client.GameLogicClient;
import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.BestMove;
import com.chess.gameservice.model.CreateGameRequest;
import com.chess.gameservice.model.GameState;
import com.chess.gameservice.model.GameSummary;
import com.chess.gameservice.model.MoveEntry;
import com.chess.gameservice.websocket.GameChannels;
import com.chess.gameservice.websocket.WsMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Casos de uso de Single Player (contrato, secciones 3.4 y 6). No guarda el estado de las partidas:
 * Game Logic es la única fuente de verdad. Aquí solo se comprueban turno y dueño, se pide la jugada
 * al bot y se avisa a los clientes conectados por WebSocket.
 */
@Service
public class SinglePlayerService {

    private static final Logger log = LoggerFactory.getLogger(SinglePlayerService.class);

    private final GameLogicClient logic;
    private final BotcitoClient bot;
    private final GameChannels channels;

    /** Un candado por partida: serializa jugadas, turno del bot y rendición. */
    private final ConcurrentMap<String, Object> locks = new ConcurrentHashMap<>();
    private final ExecutorService background = Executors.newVirtualThreadPerTaskExecutor();

    public SinglePlayerService(GameLogicClient logic, BotcitoClient bot, GameChannels channels) {
        this.logic = logic;
        this.bot = bot;
        this.channels = channels;
    }

    // ---------------------------------------------------------------- REST

    public GameState createGame(String userId, CreateGameRequest request) {
        if (request == null) {
            throw ApiException.validation("Falta el cuerpo de la petición");
        }
        String mode = request.mode();
        Integer level = null;
        String color = null;

        if ("vs_bot".equals(mode)) {
            level = request.level();
            if (level == null || level < 1 || level > 20) {
                throw ApiException.validation("level debe ser un entero de 1 a 20");
            }
            color = request.playerColor();
            if (!isColor(color)) {
                throw ApiException.validation("playerColor debe ser \"white\" o \"black\"");
            }
        } else if (!"local".equals(mode)) {
            throw ApiException.validation("mode debe ser \"local\" o \"vs_bot\"");
        }

        GameState state = logic.createGame(userId, mode, level, color);

        // Si el jugador eligió negras, el bot abre la partida antes de responder (sección 6).
        if (isBotTurn(state)) {
            synchronized (lockFor(state.gameId())) {
                state = tryBotTurn(state);
            }
        }
        return state;
    }

    public GameState getGame(String userId, String gameId) {
        return ownedGame(userId, gameId);
    }

    public List<GameSummary> listGames(String userId) {
        return logic.listGames(userId);
    }

    /** side solo hace falta en modo local; en vs_bot se usa playerColor. */
    public GameState resign(String userId, String gameId, String requestedSide) {
        synchronized (lockFor(gameId)) {
            GameState state = ownedGame(userId, gameId);

            String side;
            if (isBotGame(state)) {
                side = state.playerColor();
            } else {
                if (!isColor(requestedSide)) {
                    throw ApiException.validation("side debe ser \"white\" o \"black\" en modo local");
                }
                side = requestedSide;
            }

            GameState next = logic.resign(gameId, side);
            publish(next, null);
            return next;
        }
    }

    // ----------------------------------------------------------- WebSocket

    /** Jugada del humano por WebSocket. Todo lo que cambia se envía a los clientes conectados. */
    public void handleMove(String userId, String gameId, String uci) {
        if (uci == null || uci.isBlank()) {
            throw ApiException.validation("Falta el campo uci");
        }
        synchronized (lockFor(gameId)) {
            GameState state = ownedGame(userId, gameId);
            if (isFinished(state)) {
                throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "GAME_FINISHED", "La partida ya terminó");
            }
            if (isBotGame(state) && !state.turn().equals(state.playerColor())) {
                throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "NOT_YOUR_TURN", "No es tu turno");
            }

            GameState next = logic.move(gameId, uci);
            publish(next, lastUci(next));

            if (isBotTurn(next)) {
                tryBotTurn(next);
            }
        }
    }

    /**
     * Si al conectarse un cliente le toca mover al bot (por ejemplo, Botcito estaba caído
     * cuando se creó la partida), se retoma el turno del bot en segundo plano.
     */
    public void resumeBotIfNeeded(GameState state) {
        if (!isBotTurn(state)) {
            return;
        }
        background.execute(() -> {
            synchronized (lockFor(state.gameId())) {
                try {
                    GameState fresh = logic.getGame(state.gameId());
                    if (isBotTurn(fresh)) {
                        botTurn(fresh);
                    }
                } catch (ApiException e) {
                    channels.broadcast(state.gameId(), WsMessage.error(e.code(), e.getMessage()));
                }
            }
        });
    }

    // ------------------------------------------------------------- interno

    /** Pide la jugada a Botcito y la aplica en Game Logic. Lanza ApiException si algo falla. */
    private GameState botTurn(GameState state) {
        String gameId = state.gameId();
        channels.broadcast(gameId, WsMessage.botThinking());

        BestMove best = bot.bestMove(state.fen(), state.botLevel());
        GameState next = logic.move(gameId, best.uci());

        publish(next, lastUci(next));
        return next;
    }

    /** Igual que botTurn, pero si falla avisa a los clientes y deja la partida como estaba. */
    private GameState tryBotTurn(GameState state) {
        try {
            return botTurn(state);
        } catch (ApiException e) {
            log.warn("El turno del bot falló en la partida {}: {}", state.gameId(), e.getMessage());
            channels.broadcast(state.gameId(), WsMessage.error(e.code(), e.getMessage()));
            return state;
        }
    }

    /** Envía el state completo y, si la partida terminó, game_over justo después. */
    private void publish(GameState state, String lastMove) {
        channels.broadcast(state.gameId(), WsMessage.state(state, lastMove));
        if (isFinished(state)) {
            channels.broadcast(state.gameId(), WsMessage.gameOver(state.result(), state.endReason()));
            locks.remove(state.gameId());
        }
    }

    /** La partida debe existir y pertenecer al usuario; si no, GAME_NOT_FOUND. */
    private GameState ownedGame(String userId, String gameId) {
        GameState state = logic.getGame(gameId);
        if (state == null || !userId.equals(state.userId())) {
            throw ApiException.gameNotFound();
        }
        return state;
    }

    private Object lockFor(String gameId) {
        return locks.computeIfAbsent(gameId, id -> new Object());
    }

    private static boolean isColor(String value) {
        return "white".equals(value) || "black".equals(value);
    }

    private static boolean isBotGame(GameState state) {
        return "vs_bot".equals(state.mode());
    }

    private static boolean isFinished(GameState state) {
        return "finished".equals(state.status());
    }

    private static boolean isBotTurn(GameState state) {
        return isBotGame(state) && !isFinished(state) && !state.turn().equals(state.playerColor());
    }

    private static String lastUci(GameState state) {
        List<MoveEntry> moves = state.moves();
        return moves == null || moves.isEmpty() ? null : moves.get(moves.size() - 1).uci();
    }
}
