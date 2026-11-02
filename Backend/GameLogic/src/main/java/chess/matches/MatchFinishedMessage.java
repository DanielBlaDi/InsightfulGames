package chess.matches;

import java.util.List;

/**
 * The structure of the message to be sent to RabbitMQ when a match is finished
 */
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
