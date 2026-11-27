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

    /** Resumen visto por userId: su color solo si juega con uno (en local juega con ambos). */
    public GameSummary toSummary(Match match, String userId){
        List<String> colors = match.getParticipants().stream()
            .filter(participant -> userId.equals(participant.userId()))
            .map(Participant::color)
            .distinct()
            .toList();
        String color = colors.size() == 1 ? colors.get(0) : null;
        return new GameSummary(match.getGameId(), match.getMode(), match.getStatus(), match.getResult(),
            match.getCreatedAt().toString(), match.getMatchId(), match.getEndReason(), color);
    }
}
