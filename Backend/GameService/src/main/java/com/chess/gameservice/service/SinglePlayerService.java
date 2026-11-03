package com.chess.gameservice.service;

import com.chess.gameservice.client.BotcitoClient;
import com.chess.gameservice.client.GameLogicClient;
import com.chess.gameservice.client.GameLogicClient.CreateBody;
import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.BestMove;
import com.chess.gameservice.model.CreateGameRequest;
import com.chess.gameservice.model.GameState;
import com.chess.gameservice.model.MoveEntry;
import com.chess.gameservice.model.Participant;
import com.chess.gameservice.model.TimeControl;
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
 * Casos de uso de Single Player (contrato, sección 12). No guarda el estado de las partidas:
 * Game Logic es la única fuente de verdad. Aquí se decide quién participa y de quién es el turno
 * (a partir de participants), se pide la jugada al bot y se avisa a los clientes conectados.
 */
@Service
public class SinglePlayerService {

    private static final Logger log = LoggerFactory.getLogger(SinglePlayerService.class);

    public static final String LOCAL = "local";
    public static final String VS_BOT = "vs_bot";
    private static final String PRIVATE = "private";
    private static final String SHARED = "shared";

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

    // ---------------------------------------------------------------- REST

    /**
     * Arma el cuerpo de Game Logic según el modo: en local dos participantes con el mismo userId,
     * uno por color; en vs_bot uno solo, el humano. Si el bot abre y falla, la partida se devuelve igual.
     */
    public GameState createGame(String userId, CreateGameRequest request) {
        if (request == null) {
            throw ApiException.validation("Falta el cuerpo de la petición");
        }
        String mode = request.mode();
        Integer botLevel = null;
        List<Participant> participants;

        if (VS_BOT.equals(mode)) {
            botLevel = request.botLevel();
            if (botLevel == null || botLevel < 1 || botLevel > 20) {
                throw ApiException.validation("botLevel debe ser un entero de 1 a 20");
            }
            String color = request.playerColor();
            if (!isColor(color)) {
                throw ApiException.validation("playerColor debe ser \"white\" o \"black\"");
            }
            participants = List.of(new Participant(userId, color));
        } else if (LOCAL.equals(mode)) {
            participants = List.of(new Participant(userId, "white"), new Participant(userId, "black"));
        } else {
            throw ApiException.validation("mode debe ser \"local\" o \"vs_bot\"");
        }

        TimeControl timeControl = request.timeControl();
        if (timeControl != null && !Integer.valueOf(TimeControl.ALLOWED_MINUTES).equals(timeControl.minutes())) {
            throw ApiException.validation("timeControl debe ser null o { \"minutes\": 10 }");
        }
        String visibility = request.visibility() == null ? PRIVATE : request.visibility();
        if (!isVisibility(visibility)) {
            throw ApiException.validation("visibility debe ser \"private\" o \"shared\"");
        }

        GameState state = logic.createGame(new CreateBody(mode, timeControl, visibility, botLevel, participants));

        // Si el jugador eligió negras, el bot abre la partida antes de responder.
        if (isBotTurn(state)) {
            synchronized (lockFor(state.gameId())) {
                state = tryBotTurn(state);
            }
        }
        return state;
    }

    /** Lectura REST: participante o partida shared. */
    public GameState getGame(String userId, String gameId) {
        GameState state = singlePlayerGame(gameId);
        if (!isParticipant(state, userId) && !SHARED.equals(state.visibility())) {
            throw ApiException.gameNotFound();
        }
        return state;
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

    /** Cambia la visibilidad. Una versión vieja responde 409 VERSION_CONFLICT desde Game Logic. */
    public GameState changeVisibility(String userId, String gameId, String visibility, Integer expectedVersion) {
        if (!isVisibility(visibility)) {
            throw ApiException.validation("visibility debe ser \"private\" o \"shared\"");
        }
        if (expectedVersion == null) {
            throw ApiException.validation("Falta el campo expectedVersion");
        }
        synchronized (lockFor(gameId)) {
            getParticipantGame(userId, gameId);
            GameState next = logic.changeVisibility(gameId, visibility, expectedVersion);
            // La versión subió: las sesiones abiertas necesitan el state nuevo para seguir jugando.
            channels.broadcast(gameId, WsMessage.state(next, null));
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
        channels.broadcast(state.gameId(), WsMessage.state(state, lastMove));
        if (isFinished(state)) {
            channels.broadcast(state.gameId(), WsMessage.gameOver(state.result(), state.endReason()));
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

    private static boolean isVisibility(String value) {
        return PRIVATE.equals(value) || SHARED.equals(value);
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
