package com.chess.gameservice.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.http.HttpStatus;

import com.chess.gameservice.client.GameLogicClient;
import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.GameState;
import com.chess.gameservice.model.MoveEntry;
import com.chess.gameservice.model.Participant;
import com.chess.gameservice.model.PublishRequest;
import com.chess.gameservice.websocket.GameChannels;
import com.chess.gameservice.websocket.WsMessage;

/**
 * Pruebas del hub con Game Logic y los canales simulados (sin red). El juego (jugadas, bot, rendición,
 * visibilidad) lo orquesta el gateway; aquí solo se prueban el aviso publish, el estado inicial por
 * WebSocket y game.finished.
 */
class SinglePlayerServiceTest {

    static final String USER = "7d1f9d5e-3c2b-4f0e-9a41-0b5f6d7a8c90";
    static final String OTHER_USER = "11111111-2222-4333-8444-555555555555";
    static final String ID = "3f2b1c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d";

    private GameLogicClient logic;
    private GameChannels channels;
    private SinglePlayerService service;

    @BeforeEach
    void setUp() {
        logic = mock(GameLogicClient.class);
        channels = mock(GameChannels.class);
        service = new SinglePlayerService(logic, channels);
    }

    // ------------------------------------------------------------ fixtures

    /** GameState completo, con la cardinalidad de participants de cada modo. */
    static GameState game(String mode, List<Participant> participants, String turn, String status,
                          int version, String visibility, List<MoveEntry> moves, String result, String endReason) {
        return new GameState(ID, mode, visibility, null, participants,
                "vs_bot".equals(mode) ? 5 : null, null, null, status, turn,
                "fen-" + version, "initial-fen", Map.of("e2", List.of("e4")), moves, null, version,
                result, endReason, "2026-10-29T15:00:00Z", "finished".equals(status) ? "2026-10-29T15:20:00Z" : null);
    }

    static GameState local(String turn, int version) {
        return game("local", List.of(new Participant(USER, "white"), new Participant(USER, "black")),
                turn, "in_progress", version, "private", List.of(), null, null);
    }

    static GameState vsBot(String humanColor, String turn, int version, String lastUci) {
        List<MoveEntry> moves = lastUci == null ? List.of()
                : List.of(new MoveEntry(1, "white", "x", lastUci, "fen", "2026-10-29T15:00:05Z"));
        return game("vs_bot", List.of(new Participant(USER, humanColor)), turn, "in_progress", version,
                "private", moves, null, null);
    }

    static GameState finished(GameState base, String result, String endReason) {
        return game(base.mode(), base.participants(), base.turn(), "finished", base.version() + 1,
                base.visibility(), base.moves(), result, endReason);
    }

    private List<WsMessage> broadcasts() {
        ArgumentCaptor<WsMessage> captor = ArgumentCaptor.forClass(WsMessage.class);
        verify(channels, org.mockito.Mockito.atLeast(0)).broadcast(eq(ID), captor.capture());
        return captor.getAllValues();
    }

    private static List<String> types(List<WsMessage> messages) {
        List<String> types = new ArrayList<>();
        messages.forEach(m -> types.add(m.type()));
        return types;
    }

    // ------------------------------------------------------------ participantes (WebSocket)

    @Test
    void nonParticipantsAndMultiplayerGamesAreNotFound() {
        when(logic.getGame(ID)).thenReturn(local("white", 0));
        assertEquals("GAME_NOT_FOUND",
                assertThrows(ApiException.class, () -> service.getParticipantGame(OTHER_USER, ID)).code());

        GameState multiplayer = game("multiplayer", List.of(new Participant(USER, "white")), "white",
                "in_progress", 0, "private", List.of(), null, null);
        when(logic.getGame(ID)).thenReturn(multiplayer);
        assertEquals("GAME_NOT_FOUND",
                assertThrows(ApiException.class, () -> service.getParticipantGame(USER, ID)).code());
    }

    @Test
    void sharedGamesAreNotAccessibleByNonParticipants() {
        GameState shared = game("local", local("white", 0).participants(), "white", "in_progress", 0,
                "shared", List.of(), null, null);
        when(logic.getGame(ID)).thenReturn(shared);

        assertThrows(ApiException.class, () -> service.getParticipantGame(OTHER_USER, ID));
        assertSame(shared, service.getParticipantGame(USER, ID));
    }

    @Test
    void ownerIsAParticipantInBothModes() {
        when(logic.getGame(ID)).thenReturn(vsBot("black", "black", 1, "e2e4"));
        assertTrue(SinglePlayerService.isParticipant(service.getParticipantGame(USER, ID), USER));
    }

    // ------------------------------------------------------------ publish (gateway)

    private static PublishRequest publishOf(GameState state, String lastMove, Boolean gameOver) {
        return new PublishRequest(state, lastMove, gameOver, null);
    }

    private static PublishRequest signalOf(String type, String code, String message) {
        return new PublishRequest(null, null, null, new PublishRequest.Signal(type, code, message));
    }

    @Test
    void publishBroadcastsTheStateWithLastMoveAndNeverQueriesAnyService() {
        GameState state = vsBot("white", "black", 4, "e2e4");
        when(channels.tryAdvance(ID, 4)).thenReturn(true);

        service.applyPublish(ID, publishOf(state, "e2e4", null));

        assertEquals(List.of(WsMessage.state(state, "e2e4")), broadcasts());
        verifyNoInteractions(logic);
    }

    @Test
    void publishOfAFinishedGameSendsStateThenGameOver() {
        GameState over = finished(local("white", 2), "black", "surrender");
        when(channels.tryAdvance(eq(ID), anyInt())).thenReturn(true);

        service.applyPublish(ID, publishOf(over, null, null));

        InOrder order = inOrder(channels);
        order.verify(channels).broadcast(ID, WsMessage.state(over, null));
        order.verify(channels).broadcast(ID, WsMessage.gameOver("black", "surrender"));
        verify(channels).forget(ID);
    }

    @Test
    void publishCanSuppressGameOverForAFinishedGame() {
        GameState over = finished(local("white", 2), "black", "surrender");
        when(channels.tryAdvance(eq(ID), anyInt())).thenReturn(true);

        service.applyPublish(ID, publishOf(over, null, false));

        assertEquals(List.of(WsMessage.state(over, null)), broadcasts());
    }

    @Test
    void aStalePublishIsIgnored() {
        when(channels.tryAdvance(ID, 3)).thenReturn(false);

        service.applyPublish(ID, publishOf(local("white", 3), null, null));

        verify(channels, never()).broadcast(eq(ID), any());
    }

    @Test
    void signalsAreBroadcastWithoutAState() {
        service.applyPublish(ID, signalOf("bot_thinking", null, null));
        service.applyPublish(ID, signalOf("error", "ENGINE_BUSY", "Motores ocupados"));

        assertEquals(List.of(WsMessage.botThinking(), WsMessage.error("ENGINE_BUSY", "Motores ocupados")), broadcasts());
        verify(channels, never()).tryAdvance(anyString(), anyInt());
    }

    @Test
    void stateAndSignalInOnePublishGoInThatOrder() {
        GameState state = vsBot("white", "black", 1, "e2e4");
        when(channels.tryAdvance(ID, 1)).thenReturn(true);

        service.applyPublish(ID, new PublishRequest(state, "e2e4", null,
                new PublishRequest.Signal("error", "ENGINE_TIMEOUT", "Stockfish no respondió")));

        assertEquals(List.of("state", "error"), types(broadcasts()));
    }

    @Test
    void invalidPublishRequestsAreValidationErrors() {
        List<PublishRequest> invalid = List.of(
                new PublishRequest(null, null, null, null),
                publishOf(new GameState("otra-partida", "local", "private", null, List.of(), null, null, null,
                        "in_progress", "white", "f", "f", Map.of(), List.of(), null, 1, null, null, "t", null), null, null),
                publishOf(new GameState(ID, "local", "private", null, List.of(), null, null, null, "in_progress", "white",
                        "f", "f", Map.of(), List.of(), null, null, null, null, "t", null), null, null),
                signalOf("desconocido", null, null),
                signalOf("error", null, "sin código"),
                signalOf("error", "CODE", " "));
        for (PublishRequest request : invalid) {
            ApiException e = assertThrows(ApiException.class, () -> service.applyPublish(ID, request), String.valueOf(request));
            assertEquals("VALIDATION_ERROR", e.code());
            assertEquals(HttpStatus.BAD_REQUEST, e.status());
        }
        assertThrows(ApiException.class, () -> service.applyPublish(ID, null));
        verify(channels, never()).broadcast(eq(ID), any());
    }

    // ------------------------------------------------------------ game.finished

    @Test
    void finishedEventRereadsTheGameAndSendsStateAndGameOver() {
        GameState deleted = finished(local("white", 2), null, "account_deleted");
        when(channels.hasOpenSessions(ID)).thenReturn(true);
        when(logic.getGame(ID)).thenReturn(deleted);

        service.notifyFinished(ID);

        assertEquals(List.of(WsMessage.state(deleted, null), WsMessage.gameOver(null, "account_deleted")), broadcasts());
    }

    @Test
    void finishedEventWithoutOpenSessionsDoesNothing() {
        when(channels.hasOpenSessions(ID)).thenReturn(false);
        service.notifyFinished(ID);
        verifyNoInteractions(logic);
    }

    @Test
    void finishedEventPropagatesUnavailableButIgnoresMissingGames() {
        when(channels.hasOpenSessions(ID)).thenReturn(true);
        when(logic.getGame(ID)).thenThrow(ApiException.gameNotFound(), ApiException.unavailable("caído"));
        service.notifyFinished(ID); // 404: sin excepción, no se reintenta

        assertThrows(ApiException.class, () -> service.notifyFinished(ID));
        verify(channels, never()).broadcast(eq(ID), any());
    }
}
