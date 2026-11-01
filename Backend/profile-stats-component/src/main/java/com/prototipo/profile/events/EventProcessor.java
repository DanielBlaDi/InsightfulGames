package com.prototipo.profile.events;

import com.prototipo.profile.domain.DeletedUserRepository;
import com.prototipo.profile.domain.ProcessedEvent;
import com.prototipo.profile.domain.ProcessedEventRepository;
import com.prototipo.profile.domain.Profile;
import com.prototipo.profile.domain.ProfileRepository;
import com.prototipo.profile.domain.Stats;
import com.prototipo.profile.domain.StatsRepository;
import com.prototipo.profile.service.Ids;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.HashSet;
import java.util.Set;

/**
 * Aplica los eventos. Cada evento se procesa en una transacción: los cambios y el registro del
 * eventId se guardan juntos o no se guarda nada, así que un evento repetido no suma dos veces.
 */
@Service
public class EventProcessor {

    public enum Outcome { APPLIED, IGNORED, DUPLICATE }

    private final ProfileRepository profiles;
    private final StatsRepository stats;
    private final ProcessedEventRepository processed;
    private final DeletedUserRepository deletedUsers;
    private final EntityManager entityManager;
    private final Clock clock;

    public EventProcessor(ProfileRepository profiles, StatsRepository stats, ProcessedEventRepository processed,
                          DeletedUserRepository deletedUsers, EntityManager entityManager, Clock clock) {
        this.profiles = profiles;
        this.stats = stats;
        this.processed = processed;
        this.deletedUsers = deletedUsers;
        this.entityManager = entityManager;
        this.clock = clock;
    }

    /** Crea el perfil con contadores en cero. No recrea perfiles de cuentas borradas. */
    @Transactional
    public Outcome userRegistered(UserRegisteredEvent event) {
        if (processed.existsById(event.eventId())) {
            return Outcome.DUPLICATE;
        }
        Outcome outcome = Outcome.IGNORED;
        String userId = event.userId();
        if (!deletedUsers.existsById(userId) && !profiles.existsById(userId)) {
            entityManager.persist(new Profile(userId, event.username(), instantOr(event.occurredAt())));
            entityManager.persist(new Stats(userId));
            outcome = Outcome.APPLIED;
        }
        markProcessed(event.eventId());
        return outcome;
    }

    /**
     * Suma la partida a cada participante con perfil. Solo cuentan las partidas multiplayer
     * con resultado; local, vs_bot y expired se registran como procesadas sin sumar.
     */
    @Transactional
    public Outcome gameFinished(GameFinishedEvent event) {
        if (processed.existsById(event.eventId())) {
            return Outcome.DUPLICATE;
        }
        Outcome outcome = Outcome.IGNORED;
        if (counts(event)) {
            Set<String> seen = new HashSet<>();
            for (GameFinishedEvent.Participant p : event.participants()) {
                if (Ids.ANONYMOUS_USER.equals(p.userId()) || !seen.add(p.userId())) {
                    continue;
                }
                boolean draw = "draw".equals(event.result());
                boolean win = !draw && event.result().equals(p.color());
                // Sin fila de stats no hay perfil (la FK lo exige): el usuario se ignora.
                int updated = stats.add(p.userId(), win ? 1 : 0, !draw && !win ? 1 : 0, draw ? 1 : 0);
                if (updated > 0) {
                    outcome = Outcome.APPLIED;
                }
            }
        }
        markProcessed(event.eventId());
        return outcome;
    }

    private static boolean counts(GameFinishedEvent event) {
        return "multiplayer".equals(event.mode())
                && event.result() != null
                && Set.of("white", "black", "draw").contains(event.result())
                && !"expired".equals(event.endReason())
                && event.participants() != null;
    }

    private void markProcessed(String eventId) {
        // persist inserta siempre: si otro proceso ya guardó el eventId, la clave primaria
        // hace fallar la transacción entera y no queda nada sumado dos veces.
        entityManager.persist(new ProcessedEvent(eventId, Instant.now(clock)));
    }

    private Instant instantOr(String isoDate) {
        if (isoDate != null) {
            try {
                return Instant.parse(isoDate);
            } catch (DateTimeParseException ignored) {
                // se usa la hora actual
            }
        }
        return Instant.now(clock);
    }
}
