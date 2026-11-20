package com.chess.gameservice.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
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

/** Pruebas del servicio con Game Logic, Botcito y los canales simulados (sin red). */
class SinglePlayerServiceTest {

    static final String USER = "7d1f9d5e-3c2b-4f0e-9a41-0b5f6d7a8c90";
    static final String OTHER_USER = "11111111-2222-4333-8444-555555555555";
    static final String ID = "3f2b1c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d";

    private GameLogicClient logic;
    private BotcitoClient bot;
    private GameChannels channels;
    private SinglePlayerService service;

    @BeforeEach
    void setUp() {
        logic = mock(GameLogicClient.class);
        bot = mock(BotcitoClient.class);
        channels = mock(GameChannels.class);
        service = new SinglePlayerService(logic, bot, channels);
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

    // ------------------------------------------------------------ creación

    @Test
    void rejectsInvalidCreateRequests() {
        List<CreateGameRequest> invalid = List.of(
                new CreateGameRequest("multiplayer", null, null, null, null),
                new CreateGameRequest(null, null, null, null, null),
                new CreateGameRequest("vs_bot", null, "white", null, null),
                new CreateGameRequest("vs_bot", 0, "white", null, null),
                new CreateGameRequest("vs_bot", 21, "white", null, null),
                new CreateGameRequest("vs_bot", 5, "green", null, null),
                new CreateGameRequest("local", null, null, new TimeControl(5), null),
                new CreateGameRequest("local", null, null, new TimeControl(null), null),
                new CreateGameRequest("local", null, null, null, "public"));
        for (CreateGameRequest request : invalid) {
            ApiException e = assertThrows(ApiException.class, () -> service.createGame(USER, request), request.toString());
            assertEquals("VALIDATION_ERROR", e.code());
            assertEquals(HttpStatus.BAD_REQUEST, e.status());
        }
        assertThrows(ApiException.class, () -> service.createGame(USER, null));
        verifyNoInteractions(logic);
    }

    @Test
    void localGameSendsTwoParticipantsWithTheSameUserAndDefaultsToPrivate() {
        when(logic.createGame(any())).thenReturn(local("white", 0));

        // botLevel y playerColor se ignoran en local
        GameState state = service.createGame(USER, new CreateGameRequest("local", 7, "black", null, null));

        ArgumentCaptor<CreateBody> body = ArgumentCaptor.forClass(CreateBody.class);
        verify(logic).createGame(body.capture());
        assertEquals("local", body.getValue().mode());
        assertNull(body.getValue().botLevel());
        assertNull(body.getValue().timeControl());
        assertEquals("private", body.getValue().visibility());
        assertEquals(List.of(new Participant(USER, "white"), new Participant(USER, "black")),
                body.getValue().participants());
        assertEquals(0, state.version());
        verifyNoInteractions(bot);
    }

    @Test
    void botGameSendsOnlyTheHumanAndForwardsTimeControlAndVisibility() {
        when(logic.createGame(any())).thenReturn(vsBot("white", "white", 0, null));

        service.createGame(USER, new CreateGameRequest("vs_bot", 5, "white", new TimeControl(10), "shared"));

        ArgumentCaptor<CreateBody> body = ArgumentCaptor.forClass(CreateBody.class);
        verify(logic).createGame(body.capture());
        assertEquals(List.of(new Participant(USER, "white")), body.getValue().participants());
        assertEquals(5, body.getValue().botLevel());
        assertEquals(new TimeControl(10), body.getValue().timeControl());
        assertEquals("shared", body.getValue().visibility());
        verifyNoInteractions(bot);
    }

    @Test
    void botGameAsBlackLetsTheBotOpenWithTheCurrentVersion() {
        GameState created = vsBot("black", "white", 0, null);
        GameState afterBot = vsBot("black", "black", 1, "e2e4");
        when(logic.createGame(any())).thenReturn(created);
        when(bot.bestMove(created.fen(), 5)).thenReturn(new BestMove("e2e4", "e4", null));
        when(logic.move(ID, "e2e4", 0)).thenReturn(afterBot);

        GameState state = service.createGame(USER, new CreateGameRequest("vs_bot", 5, "black", null, null));

        assertSame(afterBot, state);
        verify(logic).move(ID, "e2e4", 0);
    }

    @Test
    void botFailureOnCreationStillReturnsTheGame() {
        GameState created = vsBot("black", "white", 0, null);
        when(logic.createGame(any())).thenReturn(created);
        when(bot.bestMove(anyString(), anyInt()))
                .thenThrow(new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "ENGINE_BUSY", "Motores ocupados"));

        GameState state = service.createGame(USER, new CreateGameRequest("vs_bot", 5, "black", null, null));

        assertSame(created, state);
        verify(logic, never()).move(anyString(), anyString(), anyInt());
        List<WsMessage> sent = broadcasts();
        assertEquals(new WsMessage.ErrorMessage("error", "ENGINE_BUSY", "Motores ocupados"), sent.get(sent.size() - 1));
    }

    // ------------------------------------------------------------ jugadas

    @Test
    void humanMoveForwardsExpectedVersionAndBotMovesWithTheNewVersion() {
        GameState start = vsBot("white", "white", 3, null);
        GameState afterHuman = vsBot("white", "black", 4, "e2e4");
        GameState afterBot = vsBot("white", "white", 5, "e7e5");
        when(logic.getGame(ID)).thenReturn(start);
        when(logic.move(ID, "e2e4", 3)).thenReturn(afterHuman);
        when(bot.bestMove(afterHuman.fen(), 5)).thenReturn(new BestMove("e7e5", "e5", null));
        when(logic.move(ID, "e7e5", 4)).thenReturn(afterBot);

        service.handleMove(USER, ID, "e2e4", 3);

        assertEquals(List.of("state", "bot_thinking", "state"), types(broadcasts()));
        assertEquals(new WsMessage.State("state", afterBot, "e7e5"), broadcasts().get(2));
    }

    @Test
    void moveWithoutExpectedVersionOrUciIsAValidationError() {
        assertEquals("VALIDATION_ERROR",
                assertThrows(ApiException.class, () -> service.handleMove(USER, ID, "e2e4", null)).code());
        assertEquals("VALIDATION_ERROR",
                assertThrows(ApiException.class, () -> service.handleMove(USER, ID, " ", 0)).code());
        verifyNoInteractions(logic);
    }

    @Test
    void versionConflictSendsTheCurrentStateBeforeRejecting() {
        GameState current = local("black", 8);
        when(logic.getGame(ID)).thenReturn(current);
        when(logic.move(ID, "e2e4", 7))
                .thenThrow(new ApiException(HttpStatus.CONFLICT, "VERSION_CONFLICT", "Versión distinta"));

        ApiException e = assertThrows(ApiException.class, () -> service.handleMove(USER, ID, "e2e4", 7));

        assertEquals("VERSION_CONFLICT", e.code());
        assertEquals(List.of(new WsMessage.State("state", current, null)), broadcasts());
    }

    @Test
    void clockExpiredSendsTheFinalStateAndGameOver() {
        GameState before = local("white", 2);
        GameState timedOut = finished(before, "black", "timeout");
        when(logic.getGame(ID)).thenReturn(before, timedOut);
        when(logic.move(ID, "e2e4", 2))
                .thenThrow(new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "CLOCK_EXPIRED", "Reloj vencido"));

        ApiException e = assertThrows(ApiException.class, () -> service.handleMove(USER, ID, "e2e4", 2));

        assertEquals("CLOCK_EXPIRED", e.code());
        assertEquals(List.of(WsMessage.state(timedOut, null), WsMessage.gameOver("black", "timeout")), broadcasts());
    }

    @Test
    void movingWhenItIsTheBotsTurnIsRejected() {
        when(logic.getGame(ID)).thenReturn(vsBot("white", "black", 1, "e2e4"));

        ApiException e = assertThrows(ApiException.class, () -> service.handleMove(USER, ID, "e7e5", 1));

        assertEquals("NOT_YOUR_TURN", e.code());
        assertEquals(HttpStatus.UNPROCESSABLE_ENTITY, e.status());
        verify(logic, never()).move(anyString(), anyString(), anyInt());
    }

    @Test
    void movingOnAFinishedGameIsRejected() {
        when(logic.getGame(ID)).thenReturn(finished(local("white", 4), "black", "checkmate"));

        ApiException e = assertThrows(ApiException.class, () -> service.handleMove(USER, ID, "e2e4", 5));

        assertEquals("GAME_FINISHED", e.code());
        verify(logic, never()).move(anyString(), anyString(), anyInt());
    }

    @Test
    void localGameAcceptsMovesFromEitherSideWithoutBot() {
        when(logic.getGame(ID)).thenReturn(local("black", 1));
        when(logic.move(ID, "e7e5", 1)).thenReturn(local("white", 2));

        service.handleMove(USER, ID, "e7e5", 1);

        verifyNoInteractions(bot);
        assertEquals(List.of("state"), types(broadcasts()));
    }

    @Test
    void mateSendsStateAndThenGameOver() {
        GameState mated = finished(local("black", 3), "black", "checkmate");
        when(logic.getGame(ID)).thenReturn(local("black", 3));
        when(logic.move(ID, "d8h4", 3)).thenReturn(mated);

        service.handleMove(USER, ID, "d8h4", 3);

        InOrder order = inOrder(channels);
        order.verify(channels).broadcast(ID, WsMessage.state(mated, null));
        order.verify(channels).broadcast(ID, WsMessage.gameOver("black", "checkmate"));
    }

    @Test
    void botFailureAfterHumanMoveKeepsTheHumanMoveAndSendsTheRealError() {
        when(logic.getGame(ID)).thenReturn(vsBot("white", "white", 0, null));
        when(logic.move(ID, "e2e4", 0)).thenReturn(vsBot("white", "black", 1, "e2e4"));
        when(bot.bestMove(anyString(), anyInt()))
                .thenThrow(new ApiException(HttpStatus.GATEWAY_TIMEOUT, "ENGINE_TIMEOUT", "Stockfish no respondió"));

        service.handleMove(USER, ID, "e2e4", 0); // no lanza: la jugada humana ya está guardada

        assertEquals(List.of("state", "bot_thinking", "error"), types(broadcasts()));
        WsMessage.ErrorMessage error = (WsMessage.ErrorMessage) broadcasts().get(2);
        assertEquals("ENGINE_TIMEOUT", error.code());
    }

    // ------------------------------------------------------------ participantes

    @Test
    void nonParticipantsAndMultiplayerGamesAreNotFound() {
        when(logic.getGame(ID)).thenReturn(local("white", 0));
        assertEquals("GAME_NOT_FOUND", assertThrows(ApiException.class, () -> service.getGame(OTHER_USER, ID)).code());
        assertEquals("GAME_NOT_FOUND",
                assertThrows(ApiException.class, () -> service.getParticipantGame(OTHER_USER, ID)).code());
        assertEquals("GAME_NOT_FOUND",
                assertThrows(ApiException.class, () -> service.handleMove(OTHER_USER, ID, "e2e4", 0)).code());
        assertEquals("GAME_NOT_FOUND",
                assertThrows(ApiException.class, () -> service.resign(OTHER_USER, ID, "white")).code());

        GameState multiplayer = game("multiplayer", List.of(new Participant(USER, "white")), "white",
                "in_progress", 0, "private", List.of(), null, null);
        when(logic.getGame(ID)).thenReturn(multiplayer);
        assertEquals("GAME_NOT_FOUND", assertThrows(ApiException.class, () -> service.getGame(USER, ID)).code());
    }

    @Test
    void sharedGamesCanBeReadButNotPlayedByNonParticipants() {
        GameState shared = game("local", local("white", 0).participants(), "white", "in_progress", 0,
                "shared", List.of(), null, null);
        when(logic.getGame(ID)).thenReturn(shared);

        assertSame(shared, service.getGame(OTHER_USER, ID));
        assertThrows(ApiException.class, () -> service.getParticipantGame(OTHER_USER, ID));
        assertSame(shared, service.getParticipantGame(USER, ID));
    }

    @Test
    void ownerIsAParticipantInBothModes() {
        when(logic.getGame(ID)).thenReturn(vsBot("black", "black", 1, "e2e4"));
        assertTrue(SinglePlayerService.isParticipant(service.getGame(USER, ID), USER));
        assertEquals("black", SinglePlayerService.humanColor(vsBot("black", "white", 0, null)));
        assertNull(SinglePlayerService.humanColor(local("white", 0)));
    }

    @Test
    void resumeDoesNothingWhenItIsTheHumansTurn() {
        service.resumeBotIfNeeded(vsBot("white", "white", 0, null));
        service.resumeBotIfNeeded(local("black", 1));
        verifyNoInteractions(logic, bot);
    }

    // ------------------------------------------------------------ rendición

    @Test
    void resignInBotGameUsesTheHumansColor() {
        GameState start = vsBot("black", "black", 1, "e2e4");
        when(logic.getGame(ID)).thenReturn(start);
        when(logic.resign(ID, "black")).thenReturn(finished(start, "white", "surrender"));

        service.resign(USER, ID, "white"); // el side enviado se ignora en vs_bot

        verify(logic).resign(ID, "black");
        assertEquals(List.of("state", "game_over"), types(broadcasts()));
    }

    @Test
    void resignInLocalGameNeedsTheSide() {
        GameState start = local("white", 0);
        when(logic.getGame(ID)).thenReturn(start);
        when(logic.resign(ID, "white")).thenReturn(finished(start, "black", "surrender"));

        assertEquals("VALIDATION_ERROR", assertThrows(ApiException.class, () -> service.resign(USER, ID, null)).code());
        service.resign(USER, ID, "white");
        verify(logic).resign(ID, "white");
    }

    // ------------------------------------------------------------ visibilidad

    @Test
    void visibilityIsForwardedWithTheExpectedVersionAndBroadcast() {
        GameState start = local("white", 4);
        GameState shared = game("local", start.participants(), "white", "in_progress", 5, "shared",
                List.of(), null, null);
        when(logic.getGame(ID)).thenReturn(start);
        when(logic.changeVisibility(ID, "shared", 4)).thenReturn(shared);

        assertSame(shared, service.changeVisibility(USER, ID, "shared", 4));
        assertEquals(List.of(WsMessage.state(shared, null)), broadcasts());
    }

    @Test
    void visibilityValidatesAndOnlyParticipantsMayChangeIt() {
        assertEquals("VALIDATION_ERROR",
                assertThrows(ApiException.class, () -> service.changeVisibility(USER, ID, "public", 1)).code());
        assertEquals("VALIDATION_ERROR",
                assertThrows(ApiException.class, () -> service.changeVisibility(USER, ID, "shared", null)).code());

        when(logic.getGame(ID)).thenReturn(local("white", 1));
        assertEquals("GAME_NOT_FOUND",
                assertThrows(ApiException.class, () -> service.changeVisibility(OTHER_USER, ID, "shared", 1)).code());
        verify(logic, never()).changeVisibility(anyString(), anyString(), anyInt());
    }

    @Test
    void visibilityVersionConflictIsPropagated() {
        when(logic.getGame(ID)).thenReturn(local("white", 4));
        when(logic.changeVisibility(ID, "shared", 3))
                .thenThrow(new ApiException(HttpStatus.CONFLICT, "VERSION_CONFLICT", "Versión distinta"));

        ApiException e = assertThrows(ApiException.class, () -> service.changeVisibility(USER, ID, "shared", 3));
        assertEquals(HttpStatus.CONFLICT, e.status());
        assertEquals("VERSION_CONFLICT", e.code());
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
