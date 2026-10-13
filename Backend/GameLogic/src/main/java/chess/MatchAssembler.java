package chess;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import chess.GameState.MoveEntry;

/**
 * Convierte una Match (lo guardado en Mongo) en los objetos JSON del contrato.
 * Antes armaba los enlaces HATEOAS; el contrato no los usa, así que ahora arma GameState y GameSummary.
 */
@Component
public class MatchAssembler{

    public GameState toState(Match match){
        //legalMoves no se guarda: se calcula desde el FEN. Vacío {} si la partida terminó
        Map<String, List<String>> legalMoves = match.isFinished() ? Map.of() : ChessRules.legalMoves(match.getFen());

        List<MoveEntry> moves = new ArrayList<>();
        for(Movement movement : match.getMovements()){
            moves.add(new MoveEntry(movement.getPly(), movement.getSan(), movement.getUci(), movement.getFenAfter(), movement.getTimestamp().toString()));
        }

        return new GameState(
            match.getId(),
            match.getUserId(),
            match.getMode(),
            match.getBotLevel(),
            match.getPlayerColor(),
            match.getStatus(),
            match.getTurn(),
            match.getFen(),
            legalMoves,
            moves,
            match.getResult(),
            match.getEndReason(),
            match.getCreatedAt().toString(),
            match.getFinishedAt() == null ? null : match.getFinishedAt().toString()
        );
    }

    public GameSummary toSummary(Match match){
        return new GameSummary(match.getId(), match.getMode(), match.getStatus(), match.getResult(), match.getCreatedAt().toString());
    }
}
