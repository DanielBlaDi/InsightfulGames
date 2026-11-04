package chess.matches;

import java.util.List;

/** Evento game.finished (contrato, 19.6.2). eventId es también el messageId de AMQP. */
public record MatchFinishedMessage(
    String eventId,
    String eventType,
    String occurredAt,
    String gameId,
    String matchId,
    String mode,
    List<Participant> participants,
    String result,
    String endReason,
    String finishedAt
){}
