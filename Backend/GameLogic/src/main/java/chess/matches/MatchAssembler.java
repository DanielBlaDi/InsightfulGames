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
        Map<String, List<String>> legalMoves = !match.canBeOperatedOn() ? Map.of() : ChessRules.legalMoves(match.getFen());

        List<MoveEntry> moves = new ArrayList<>();
        for(Movement movement : match.getMovements()){
            moves.add(new MoveEntry(movement.getPly(), movement.getSan(), movement.getUci(), movement.getFenAfter(), movement.getTimestamp().toString(), movement.getColor()));
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
            match.getVersion(),
            match.getResult(),
            match.getEndReason(),
            match.getCreatedAt().toString(),
            match.getFinishedAt() == null ? null : match.getFinishedAt().toString()
        );
    }

    /** color es el del usuario que pide la lista; null en local, donde juega con los dos colores. */
    public GameSummary toSummary(Match match, String userId){
        String color = null;
        if(!chess.constants.Mode.LOCAL.toString().equals(match.getMode())){
            Participant participant = match.participantWithUserId(userId);
            color = participant == null ? null : participant.color();
        }
        return new GameSummary(match.getGameId(), match.getMode(), match.getMatchId(), match.getStatus(), match.getResult(),
            match.getEndReason(), color, match.getCreatedAt().toString());
    }
}
