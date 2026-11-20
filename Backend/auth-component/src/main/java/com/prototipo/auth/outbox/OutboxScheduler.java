package com.prototipo.auth.outbox;

import com.prototipo.auth.events.UserRegistered;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * Cuándo se publica el outbox: enseguida después de cada registro confirmado (sin hacer esperar
 * la respuesta HTTP) y, como respaldo, cada cierto tiempo, para lo que quedó pendiente porque
 * RabbitMQ no estaba disponible. Se desactiva con outbox.scheduler.enabled=false (pruebas).
 */
@Configuration
@EnableScheduling
@EnableAsync
@ConditionalOnProperty(name = "outbox.scheduler.enabled", havingValue = "true", matchIfMissing = true)
public class OutboxScheduler {

    private final OutboxRelay relay;

    public OutboxScheduler(OutboxRelay relay) {
        this.relay = relay;
    }

    @Async
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterRegistration(UserRegistered registered) {
        relay.publishPending();
    }

    @Scheduled(fixedDelayString = "${outbox.relay-interval-ms:2000}", initialDelayString = "${outbox.relay-interval-ms:2000}")
    public void publishPending() {
        relay.publishPending();
    }

    @Scheduled(fixedDelayString = "PT1H")
    public void purgePublished() {
        relay.purgePublished();
    }
}
