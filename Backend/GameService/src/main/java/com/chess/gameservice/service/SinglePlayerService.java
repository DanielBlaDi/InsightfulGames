package com.chess.gameservice.service;

import com.chess.gameservice.client.GameLogicClient;
import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.GameState;
import com.chess.gameservice.model.Participant;
import com.chess.gameservice.model.PublishRequest;
import com.chess.gameservice.websocket.GameChannels;
import com.chess.gameservice.websocket.WsMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * Hub de sesiones de Single Player (contrato, sección 12). No guarda el estado de las partidas: Game
 * Logic es la única fuente de verdad, y tampoco decide nada del juego. Todo lo que cambia una partida
 * (crear, jugar, turno del bot, rendirse, cambiar la visibilidad) lo orquesta el gateway web contra
 * Game Logic y Botcito, y avisa aquí con {@link #applyPublish}. Este servicio solo mantiene las sesiones
 * WebSocket, envía el estado inicial a quien se conecta y avisa del fin de partida (game.finished).
 */
@Service
public class SinglePlayerService {

    private static final Logger log = LoggerFactory.getLogger(SinglePlayerService.class);

    public static final String LOCAL = "local";
    public static final String VS_BOT = "vs_bot";

    private final GameLogicClient logic;
    private final GameChannels channels;

    public SinglePlayerService(GameLogicClient logic, GameChannels channels) {
        this.logic = logic;
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
            }
        }
        if (signal != null) {
            channels.broadcast(gameId, "bot_thinking".equals(signal.type())
                    ? WsMessage.botThinking()
                    : WsMessage.error(signal.code(), signal.message()));
        }
    }

    // ----------------------------------------------------------- WebSocket

    /** Partida en la que el usuario participa (para el WebSocket); si no, GAME_NOT_FOUND. */
    public GameState getParticipantGame(String userId, String gameId) {
        GameState state = singlePlayerGame(gameId);
        if (!isParticipant(state, userId)) {
            throw ApiException.gameNotFound();
        }
        return state;
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
        if (state.version() != null) {
            channels.tryAdvance(gameId, state.version()); // mantiene al día la guarda de orden
        }
        channels.broadcast(gameId, WsMessage.state(state, null));
        if (isFinished(state)) {
            channels.broadcast(gameId, WsMessage.gameOver(state.result(), state.endReason()));
            channels.forget(gameId);
        }
    }

    // ------------------------------------------------------------- interno

    /** La partida debe existir y ser local o vs_bot; las multijugador no son de este servicio. */
    private GameState singlePlayerGame(String gameId) {
        GameState state = logic.getGame(gameId);
        if (!LOCAL.equals(state.mode()) && !VS_BOT.equals(state.mode())) {
            throw ApiException.gameNotFound();
        }
        return state;
    }

    static boolean isParticipant(GameState state, String userId) {
        List<Participant> participants = state.participants();
        return userId != null && participants != null
                && participants.stream().anyMatch(p -> userId.equals(p.userId()));
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static boolean isFinished(GameState state) {
        return "finished".equals(state.status());
    }
}
