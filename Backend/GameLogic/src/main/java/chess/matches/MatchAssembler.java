package chess.matches;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import chess.matches.GameState.MoveEntry;
import chess.movements.Movement;

/**
 * Convierte una Match (lo guardado en Mongo) en los objetos JSON del contrato.
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
            match.getGameId(),
            match.getMode(),
            match.getVisibility(),
            match.getMatchId(),
            match.getParticipants(),
            match.getBotLevel(),
            match.getTimeControl(),
            match.getClocks(),
            match.getStatus(),
            match.getTurn(),
            match.getFen(),
            match.getInitialFen(),
            legalMoves,
            moves,
            match.getDrawOffer(),
            match.getExpectedVersion(),
            match.getResult(),
            match.getEndReason(),
            match.getCreatedAt().toString(),
            match.getFinishedAt() == null ? null : match.getFinishedAt().toString()
        );
    }

    public GameSummary toSummary(Match match){
        return new GameSummary(match.getGameId(), match.getMode(), match.getStatus(), match.getResult(), match.getCreatedAt().toString());
    }
}
