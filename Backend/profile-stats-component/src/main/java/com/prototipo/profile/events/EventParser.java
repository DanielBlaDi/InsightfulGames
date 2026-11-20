package com.prototipo.profile.events;

import com.prototipo.profile.service.Ids;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

import java.util.Set;

/** Convierte el cuerpo JSON de un mensaje en evento y comprueba los campos que se usan. */
@Component
public class EventParser {

    private static final Set<String> COLORS = Set.of("white", "black");

    private final JsonMapper mapper;

    public EventParser(JsonMapper mapper) {
        this.mapper = mapper;
    }

    public UserRegisteredEvent userRegistered(byte[] body) {
        UserRegisteredEvent event = read(body, UserRegisteredEvent.class);
        requireType(event.eventType(), "user.registered");
        requireUuid(event.eventId(), "eventId");
        requireUuid(event.userId(), "userId");
        if (event.username() == null || event.username().isBlank() || event.username().length() > 20) {
            throw new InvalidEventException("username debe tener entre 1 y 20 caracteres");
        }
        return event;
    }

    public GameFinishedEvent gameFinished(byte[] body) {
        GameFinishedEvent event = read(body, GameFinishedEvent.class);
        requireType(event.eventType(), "game.finished");
        requireUuid(event.eventId(), "eventId");
        if (event.mode() == null) {
            throw new InvalidEventException("Falta mode");
        }
        if (event.participants() != null) {
            for (GameFinishedEvent.Participant p : event.participants()) {
                if (p == null || !Ids.isUuid(p.userId()) || !COLORS.contains(p.color())) {
                    throw new InvalidEventException("participants debe tener userId UUID y color white o black");
                }
            }
        }
        return event;
    }

    private <T> T read(byte[] body, Class<T> type) {
        try {
            T event = mapper.readValue(body, type);
            if (event == null) {
                throw new InvalidEventException("Mensaje vacío");
            }
            return event;
        } catch (InvalidEventException e) {
            throw e;
        } catch (RuntimeException e) {
            throw new InvalidEventException("El mensaje no es un JSON válido", e);
        }
    }

    /** eventType es obligatorio en el contrato; si viene distinto, el mensaje llegó a la cola equivocada. */
    private static void requireType(String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new InvalidEventException("eventType debe ser " + expected);
        }
    }

    private static void requireUuid(String value, String field) {
        if (!Ids.isUuid(value)) {
            throw new InvalidEventException(field + " debe ser un UUID");
        }
    }
}
