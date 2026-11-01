package com.prototipo.profile.events;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;

/** game.finished (sección 17). Profile/Stats solo usa mode, participants, result y endReason. */
@JsonIgnoreProperties(ignoreUnknown = true)
public record GameFinishedEvent(String eventId, String eventType, String occurredAt, String gameId,
                                String matchId, String mode, List<Participant> participants,
                                String result, String endReason, String finishedAt) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Participant(String userId, String color) {
    }
}
