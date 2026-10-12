package com.chess.gameservice.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpStatus;

import com.chess.gameservice.client.BotcitoClient;
import com.chess.gameservice.client.GameLogicClient;
import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.BestMove;
import com.chess.gameservice.model.CreateGameRequest;
import com.chess.gameservice.model.GameState;
import com.chess.gameservice.model.MoveEntry;
import com.chess.gameservice.websocket.GameChannels;
import com.chess.gameservice.websocket.WsMessage;

/** Pruebas del servicio con Game Logic, Botcito y los canales simulados (sin red). */
class SinglePlayerServiceTest {

    private static final String USER = "7d1f9d5e-3c2b-4f0e-9a41-0b5f6d7a8c90";
    private static final String OTHER_USER = "11111111-2222-4333-8444-555555555555";
    private static final String ID = "game-1";

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

    private static GameState local(String turn) {
        return new GameState(ID, USER, "local", null, null, "in_progress", turn, "fen", Map.of(),
                List.of(), null, null, "2026-10-10T15:00:00Z", null);
    }

    private static GameState vsBot(String playerColor, String turn, String lastUci) {
        List<MoveEntry> moves = lastUci == null ? List.of() : List.of(new MoveEntry(1, "x", lastUci, "fen2", "t"));
        return new GameState(ID, USER, "vs_bot", 8, playerColor, "in_progress", turn, "fen", Map.of(),
                moves, null, null, "2026-10-10T15:00:00Z", null);
    }

    private static GameState finished(String result) {
        List<MoveEntry> moves = List.of(new MoveEntry(1, "Qh4#", "d8h4", "fen2", "t"));
        return new GameState(ID, USER, "local", null, null, "finished", "white", "fen", Map.of(),
                moves, result, "checkmate", "2026-10-10T15:00:00Z", "2026-10-10T15:10:00Z");
    }

    private List<String> broadcastTypes() {
        ArgumentCaptor<WsMessage> captor = ArgumentCaptor.forClass(WsMessage.class);
        verify(channels, org.mockito.Mockito.atLeast(0)).broadcast(eq(ID), captor.capture());
        return captor.getAllValues().stream().map(WsMessage::type).toList();
    }

    @Test
    void rejectsInvalidCreateRequests() {
        ApiException badMode = assertThrows(ApiException.class,
                () -> service.createGame(USER, new CreateGameRequest("online", null, null)));
        assertEquals("VALIDATION_ERROR", badMode.code());

        ApiException badLevel = assertThrows(ApiException.class,
                () -> service.createGame(USER, new CreateGameRequest("vs_bot", 99, "white")));
        assertEquals("VALIDATION_ERROR", badLevel.code());

        ApiException badColor = assertThrows(ApiException.class,
                () -> service.createGame(USER, new CreateGameRequest("vs_bot", 8, "red")));
        assertEquals("VALIDATION_ERROR", badColor.code());

        verifyNoInteractions(logic);
    }

    @Test
    void localGameIsCreatedWithoutBotFields() {
        when(logic.createGame(USER, "local", null, null)).thenReturn(local("white"));

        GameState created = service.createGame(USER, new CreateGameRequest("local", 5, "black"));

        assertEquals("local", created.mode());
        verify(logic).createGame(USER, "local", null, null);
        verifyNoInteractions(bot);
    }

    @Test
    void botGameAsWhiteDoesNotCallBot() {
        when(logic.createGame(USER, "vs_bot", 8, "white")).thenReturn(vsBot("white", "white", null));

        service.createGame(USER, new CreateGameRequest("vs_bot", 8, "white"));

        verifyNoInteractions(bot);
    }

    @Test
    void botGameAsBlackLetsTheBotOpenBeforeResponding() {
        when(logic.createGame(USER, "vs_bot", 8, "black")).thenReturn(vsBot("black", "white", null));
        when(bot.bestMove("fen", 8)).thenReturn(new BestMove("e2e4", "e4", null));
        when(logic.move(ID, "e2e4")).thenReturn(vsBot("black", "black", "e2e4"));

        GameState created = service.createGame(USER, new CreateGameRequest("vs_bot", 8, "black"));

        assertEquals("black", created.turn());
        assertEquals(1, created.moves().size());
        verify(logic).move(ID, "e2e4");
    }

    @Test
    void botFailureOnCreationStillReturnsTheGame() {
        when(logic.createGame(USER, "vs_bot", 8, "black")).thenReturn(vsBot("black", "white", null));
        when(bot.bestMove(anyString(), anyInt()))
                .thenThrow(new ApiException(HttpStatus.BAD_GATEWAY, "BOT_UNAVAILABLE", "Botcito caído"));

        GameState created = service.createGame(USER, new CreateGameRequest("vs_bot", 8, "black"));

        assertEquals("white", created.turn());
        assertTrue(broadcastTypes().contains("error"));
    }

    @Test
    void humanMoveIsFollowedByBotThinkingAndBotMove() {
        when(logic.getGame(ID)).thenReturn(vsBot("white", "white", null));
        when(logic.move(ID, "e2e4")).thenReturn(vsBot("white", "black", "e2e4"));
        when(bot.bestMove("fen", 8)).thenReturn(new BestMove("e7e5", "e5", null));
        when(logic.move(ID, "e7e5")).thenReturn(vsBot("white", "white", "e7e5"));

        service.handleMove(USER, ID, "e2e4");

        assertEquals(List.of("state", "bot_thinking", "state"), broadcastTypes());
        verify(logic).move(ID, "e7e5");
    }

    @Test
    void movingWhenItIsTheBotsTurnIsRejected() {
        when(logic.getGame(ID)).thenReturn(vsBot("white", "black", "e2e4"));

        ApiException e = assertThrows(ApiException.class, () -> service.handleMove(USER, ID, "e7e5"));

        assertEquals("NOT_YOUR_TURN", e.code());
        assertEquals(HttpStatus.UNPROCESSABLE_ENTITY, e.status());
        verify(logic, never()).move(anyString(), anyString());
    }

    @Test
    void movingOnAFinishedGameIsRejected() {
        when(logic.getGame(ID)).thenReturn(finished("black"));

        ApiException e = assertThrows(ApiException.class, () -> service.handleMove(USER, ID, "e2e4"));

        assertEquals("GAME_FINISHED", e.code());
    }

    @Test
    void localGameAcceptsMovesFromEitherSideWithoutBot() {
        when(logic.getGame(ID)).thenReturn(local("white"));
        when(logic.move(ID, "e2e4")).thenReturn(local("black"));

        service.handleMove(USER, ID, "e2e4");

        verifyNoInteractions(bot);
        assertEquals(List.of("state"), broadcastTypes());
    }

    @Test
    void mateSendsStateAndThenGameOver() {
        when(logic.getGame(ID)).thenReturn(local("black"));
        when(logic.move(ID, "d8h4")).thenReturn(finished("black"));

        service.handleMove(USER, ID, "d8h4");

        assertEquals(List.of("state", "game_over"), broadcastTypes());
    }

    @Test
    void botFailureAfterHumanMoveDoesNotFailTheMove() {
        when(logic.getGame(ID)).thenReturn(vsBot("white", "white", null));
        when(logic.move(ID, "e2e4")).thenReturn(vsBot("white", "black", "e2e4"));
        when(bot.bestMove(anyString(), anyInt()))
                .thenThrow(new ApiException(HttpStatus.BAD_GATEWAY, "BOT_UNAVAILABLE", "Botcito caído"));

        service.handleMove(USER, ID, "e2e4");

        List<String> types = broadcastTypes();
        assertEquals("state", types.get(0));
        assertTrue(types.contains("error"));
    }

    @Test
    void gamesOfOtherUsersAreNotFound() {
        when(logic.getGame(ID)).thenReturn(local("white"));

        ApiException e = assertThrows(ApiException.class, () -> service.getGame(OTHER_USER, ID));
        assertEquals("GAME_NOT_FOUND", e.code());
        assertEquals(HttpStatus.NOT_FOUND, e.status());

        assertThrows(ApiException.class, () -> service.handleMove(OTHER_USER, ID, "e2e4"));
        assertThrows(ApiException.class, () -> service.resign(OTHER_USER, ID, "white"));
        verify(logic, never()).move(anyString(), anyString());
        verify(logic, never()).resign(anyString(), anyString());
    }

    @Test
    void resignInBotGameUsesThePlayersColor() {
        when(logic.getGame(ID)).thenReturn(vsBot("black", "white", null));
        when(logic.resign(eq(ID), anyString())).thenReturn(finished("white"));

        service.resign(USER, ID, null);

        verify(logic).resign(ID, "black");
        assertEquals(List.of("state", "game_over"), broadcastTypes());
    }

    @Test
    void resignInLocalGameNeedsTheSide() {
        when(logic.getGame(ID)).thenReturn(local("white"));
        when(logic.resign(ID, "white")).thenReturn(finished("black"));

        ApiException e = assertThrows(ApiException.class, () -> service.resign(USER, ID, null));
        assertEquals("VALIDATION_ERROR", e.code());

        service.resign(USER, ID, "white");
        verify(logic).resign(ID, "white");
        verify(logic, never()).resign(eq(ID), eq("black"));
        verify(logic, never()).createGame(any(), any(), any(), any());
    }
}
