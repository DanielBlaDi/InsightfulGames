package com.chess.gameservice.service;

import com.chess.gameservice.client.BotcitoClient;
import com.chess.gameservice.client.GameLogicClient;
import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.BestMove;
import com.chess.gameservice.model.GameState;
import com.chess.gameservice.model.MoveEntry;
import com.chess.gameservice.model.Participant;
import com.chess.gameservice.model.PublishRequest;
import com.chess.gameservice.websocket.GameChannels;
import com.chess.gameservice.websocket.WsMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Hub de sesiones de Single Player (contrato, sección 12). No guarda el estado de las partidas: Game
 * Logic es la única fuente de verdad. Las operaciones REST (crear, leer, rendirse, cambiar la
 * visibilidad) las orquesta el gateway, que avisa aquí con {@link #applyPublish}. Mientras los frames
 * WebSocket sigan llegando a este servicio (se moverán al gateway), también decide de quién es el turno
 * y pide la jugada al bot.
 */
@Service
public class SinglePlayerService {

    private static final Logger log = LoggerFactory.getLogger(SinglePlayerService.class);

    public static final String LOCAL = "local";
    public static final String VS_BOT = "vs_bot";

    private final GameLogicClient logic;
    private final BotcitoClient bot;
    private final GameChannels channels;

    /** Un candado por partida: serializa jugadas, turno del bot, rendición y visibilidad. */
    private final ConcurrentMap<String, Object> locks = new ConcurrentHashMap<>();
    private final ExecutorService background = Executors.newVirtualThreadPerTaskExecutor();

    public SinglePlayerService(GameLogicClient logic, BotcitoClient bot, GameChannels channels) {
        this.logic = logic;
        this.bot = bot;
        this.channels = channels;
    }

    // ------------------------------------------------------------ publish (gateway)

    /**
     * El gateway operó en Game Logic y avisa aquí. Se envía a los clientes conectados sin consultar a
     * nadie. Un state con una version menor que la última enviada se ignora: un aviso atrasado no debe
     * hacer retroceder al cliente (el expectedVersion de Game Logic sigue siendo la guarda real).
     */
    public void applyPublish(String gameId, PublishRequest request) {
        if (request == null || (request.state() == null && request.signal() == null)) {
            throw ApiException.validation("Falta state o signal");
        }

        GameState state = request.state();
        if (state != null) {
            if (!gameId.equals(state.gameId())) {
                throw ApiException.validation("state.gameId no coincide con la partida de la ruta");
            }
            if (state.version() == null) {
                throw ApiException.validation("state.version es obligatorio");
            }
        }
        PublishRequest.Signal signal = request.signal();
        if (signal != null) {
            if (!"bot_thinking".equals(signal.type()) && !"error".equals(signal.type())) {
                throw ApiException.validation("signal.type debe ser bot_thinking o error");
            }
            if ("error".equals(signal.type()) && (isBlank(signal.code()) || isBlank(signal.message()))) {
                throw ApiException.validation("signal de tipo error necesita code y message");
            }
        }

        if (state != null) {
            if (!channels.tryAdvance(gameId, state.version())) {
                log.debug("publish de la partida {} ignorado: sin sesiones o version {} atrasada", gameId, state.version());
                return;
            }
            boolean announceGameOver = request.gameOver() == null || request.gameOver();
            channels.broadcast(gameId, WsMessage.state(state, request.lastMove()));
            if (isFinished(state)) {
                if (announceGameOver) {
                    channels.broadcast(gameId, WsMessage.gameOver(state.result(), state.endReason()));
                }
                channels.forget(gameId);
                locks.remove(gameId);
            }
        }
        if (signal != null) {
            channels.broadcast(gameId, "bot_thinking".equals(signal.type())
                    ? WsMessage.botThinking()
                    : WsMessage.error(signal.code(), signal.message()));
        }
    }

    /** Partida en la que el usuario participa (acciones y WebSocket); si no, GAME_NOT_FOUND. */
    public GameState getParticipantGame(String userId, String gameId) {
        GameState state = singlePlayerGame(gameId);
        if (!isParticipant(state, userId)) {
            throw ApiException.gameNotFound();
        }
        return state;
    }

    /** side solo hace falta en modo local; en vs_bot se usa el color del humano. */
    public GameState resign(String userId, String gameId, String requestedSide) {
        synchronized (lockFor(gameId)) {
            GameState state = getParticipantGame(userId, gameId);

            String side;
            if (isBotGame(state)) {
                side = humanColor(state);
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
    public void handleMove(String userId, String gameId, String uci, Integer expectedVersion) {
        if (uci == null || uci.isBlank()) {
            throw ApiException.validation("Falta el campo uci");
        }
        if (expectedVersion == null) {
            throw ApiException.validation("Falta el campo expectedVersion");
        }
        synchronized (lockFor(gameId)) {
            GameState state = getParticipantGame(userId, gameId);
            if (isFinished(state)) {
                throw ApiException.gameFinished();
            }
            if (isBotGame(state) && !state.turn().equals(humanColor(state))) {
                throw ApiException.notYourTurn();
            }

            GameState next;
            try {
                next = logic.move(gameId, uci, expectedVersion);
            } catch (ApiException e) {
                // El cliente tenía un estado viejo, o el reloj venció y la partida terminó:
                // se le envía el state actual (y game_over si terminó) antes del move_rejected.
                if ("VERSION_CONFLICT".equals(e.code()) || "CLOCK_EXPIRED".equals(e.code())) {
                    resync(gameId);
                }
                throw e;
            }
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

    // ------------------------------------------------------------- eventos

    /**
     * game.finished de una partida local o vs_bot: relee la partida y envía state y game_over a las
     * sesiones abiertas. Es repetible: sin sesiones abiertas no hace nada. Un 4xx de Game Logic
     * (partida inexistente) no se reintenta; los fallos de red o 5xx se propagan para reintentar.
     */
    public void notifyFinished(String gameId) {
        if (!channels.hasOpenSessions(gameId)) {
            return;
        }
        synchronized (lockFor(gameId)) {
            GameState state;
            try {
                state = logic.getGame(gameId);
            } catch (ApiException e) {
                if (e.status().is4xxClientError()) {
                    log.warn("game.finished de la partida {} sin partida legible: {}", gameId, e.getMessage());
                    return;
                }
                throw e;
            }
            publish(state, null);
        }
    }

    // ------------------------------------------------------------- interno

    /** Pide la jugada a Botcito y la aplica en Game Logic. Lanza ApiException si algo falla. */
    private GameState botTurn(GameState state) {
        String gameId = state.gameId();
        channels.broadcast(gameId, WsMessage.botThinking());

        BestMove best = bot.bestMove(state.fen(), state.botLevel());
        GameState next = logic.move(gameId, best.uci(), state.version());

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
        if (state.version() != null) {
            channels.tryAdvance(state.gameId(), state.version()); // mantiene al día la guarda de orden
        }
        channels.broadcast(state.gameId(), WsMessage.state(state, lastMove));
        if (isFinished(state)) {
            channels.broadcast(state.gameId(), WsMessage.gameOver(state.result(), state.endReason()));
            channels.forget(state.gameId());
            locks.remove(state.gameId());
        }
    }

    /** Reenvía el estado actual a las sesiones abiertas; si no se puede leer, no hace nada. */
    private void resync(String gameId) {
        try {
            publish(logic.getGame(gameId), null);
        } catch (ApiException e) {
            log.warn("No se pudo releer la partida {}: {}", gameId, e.getMessage());
        }
    }

    /** La partida debe existir y ser local o vs_bot; las multijugador no son de este servicio. */
    private GameState singlePlayerGame(String gameId) {
        GameState state = logic.getGame(gameId);
        if (!LOCAL.equals(state.mode()) && !VS_BOT.equals(state.mode())) {
            throw ApiException.gameNotFound();
        }
        return state;
    }

    private Object lockFor(String gameId) {
        return locks.computeIfAbsent(gameId, id -> new Object());
    }

    static boolean isParticipant(GameState state, String userId) {
        List<Participant> participants = state.participants();
        return userId != null && participants != null
                && participants.stream().anyMatch(p -> userId.equals(p.userId()));
    }

    /**
     * Color del humano en vs_bot: el de su única entrada en participants. null si la partida
     * no es vs_bot o no respeta esa cardinalidad.
     */
    static String humanColor(GameState state) {
        List<Participant> participants = state.participants();
        if (!isBotGame(state) || participants == null || participants.size() != 1) {
            return null;
        }
        return participants.get(0).color();
    }

    private static boolean isColor(String value) {
        return "white".equals(value) || "black".equals(value);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static boolean isBotGame(GameState state) {
        return VS_BOT.equals(state.mode());
    }

    private static boolean isFinished(GameState state) {
        return "finished".equals(state.status());
    }

    /** Turno del bot: vs_bot en curso y el turno no es el del humano. */
    private static boolean isBotTurn(GameState state) {
        String human = humanColor(state);
        return human != null && "in_progress".equals(state.status()) && !human.equals(state.turn());
    }

    private static String lastUci(GameState state) {
        List<MoveEntry> moves = state.moves();
        return moves == null || moves.isEmpty() ? null : moves.get(moves.size() - 1).uci();
    }
}
