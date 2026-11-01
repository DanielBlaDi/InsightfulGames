package com.prototipo.profile.events;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** user.registered (sección 17). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record UserRegisteredEvent(String eventId, String eventType, String occurredAt,
                                  String userId, String username) {
}
