package com.prototipo.auth.outbox;

import com.prototipo.auth.events.UserEventsTopology;
import com.prototipo.auth.events.UserRegistered;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/** Guarda user.registered (sección 17) en el outbox, dentro de la transacción del registro. */
@Component
public class UserRegisteredOutbox {

    private final OutboxRepository outbox;
    private final JsonMapper mapper;
    private final Clock clock;

    public UserRegisteredOutbox(OutboxRepository outbox, JsonMapper mapper, Clock clock) {
        this.outbox = outbox;
        this.mapper = mapper;
        this.clock = clock;
    }

    /** MANDATORY: sin la transacción del registro no se garantiza que usuario y evento vayan juntos. */
    @Transactional(propagation = Propagation.MANDATORY)
    public void record(UserRegistered registered) {
        Instant now = Instant.now(clock);
        String eventId = UUID.randomUUID().toString();
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("eventId", eventId);
        event.put("eventType", UserEventsTopology.USER_REGISTERED);
        event.put("occurredAt", now.truncatedTo(ChronoUnit.SECONDS).toString());
        event.put("userId", registered.userId());
        event.put("username", registered.username());
        outbox.save(new OutboxEvent(eventId, UserEventsTopology.USER_EVENTS, UserEventsTopology.USER_REGISTERED,
                mapper.writeValueAsString(event), now));
    }
}
