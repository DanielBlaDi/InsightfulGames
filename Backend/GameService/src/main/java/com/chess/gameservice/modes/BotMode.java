package com.chess.gameservice.modes;

import com.chess.gameservice.client.BotcitoClient;
import com.chess.gameservice.protocol.ServerMessage;
import com.chess.gameservice.session.GameSession;
import org.springframework.stereotype.Component;

import java.util.function.BiConsumer;

/** Modo contra el bot: pide la jugada a Botcito sin bloquear el hilo del WebSocket. */
@Component
public class BotMode {

    private final BotcitoClient botcito;

    public BotMode(BotcitoClient botcito) {
        this.botcito = botcito;
    }

    public void requestMove(GameSession session, BiConsumer<GameSession, String> onMove) {
        botcito.bestMove(session.fen(), session.difficulty())
                .thenAccept(move -> onMove.accept(session, move))
                .exceptionally(ex -> {
                    session.send(ServerMessage.error("Botcito no pudo responder: " + ex.getMessage()));
                    return null;
                });
    }
}
