package com.prototipo.auth.outbox;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.locks.ReentrantLock;

/**
 * Publica los eventos pendientes del outbox, en orden. Un evento se marca como publicado solo
 * después de la confirmación del broker; si Auth cae entre la confirmación y la marca, el evento
 * se vuelve a enviar con el mismo eventId y los consumidores lo descartan (son idempotentes).
 */
@Component
public class OutboxRelay {

    private static final Logger log = LoggerFactory.getLogger(OutboxRelay.class);
    /** Los eventos publicados se guardan un tiempo para poder revisarlos y luego se borran. */
    static final Duration RETENTION = Duration.ofDays(7);

    private final OutboxRepository outbox;
    private final EventSender sender;
    private final Clock clock;
    private final ReentrantLock running = new ReentrantLock();

    public OutboxRelay(OutboxRepository outbox, EventSender sender, Clock clock) {
        this.outbox = outbox;
        this.sender = sender;
        this.clock = clock;
    }

    /**
     * Intenta publicar los pendientes y devuelve cuántos publicó. Se detiene en el primer fallo:
     * casi siempre significa que el broker no está, y así no se desordenan los eventos.
     */
    public int publishPending() {
        if (!running.tryLock()) {
            return 0; // ya hay una pasada en curso en esta instancia
        }
        try {
            int published = 0;
            for (OutboxEvent event : outbox.findTop50ByPublishedAtIsNullOrderByCreatedAtAsc()) {
                try {
                    sender.send(event);
                } catch (RuntimeException e) {
                    event.markFailed(e.toString());
                    outbox.save(event);
                    log.warn("No se pudo publicar {} (intento {}): {}", event.getEventId(), event.getAttempts(), e.toString());
                    break;
                }
                event.markPublished(Instant.now(clock));
                outbox.save(event);
                published++;
            }
            return published;
        } finally {
            running.unlock();
        }
    }

    public int purgePublished() {
        return outbox.deletePublishedBefore(Instant.now(clock).minus(RETENTION));
    }
}
