package com.prototipo.auth.outbox;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/** Evento pendiente de publicar en RabbitMQ. Se guarda en la misma transacción que el cambio. */
@Entity
@Table(name = "outbox_events")
public class OutboxEvent {

    @Id
    @Column(name = "event_id", nullable = false, length = 36)
    private String eventId;

    @Column(name = "exchange_name", nullable = false, length = 100)
    private String exchange;

    @Column(name = "routing_key", nullable = false, length = 100)
    private String routingKey;

    @Column(name = "payload", nullable = false, columnDefinition = "TEXT")
    private String payload;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "published_at")
    private Instant publishedAt;

    @Column(name = "attempts", nullable = false)
    private int attempts;

    @Column(name = "last_error", length = 500)
    private String lastError;

    protected OutboxEvent() {
        // Constructor requerido por JPA.
    }

    public OutboxEvent(String eventId, String exchange, String routingKey, String payload, Instant createdAt) {
        this.eventId = eventId;
        this.exchange = exchange;
        this.routingKey = routingKey;
        this.payload = payload;
        this.createdAt = createdAt;
    }

    public void markPublished(Instant when) {
        this.publishedAt = when;
        this.lastError = null;
    }

    public void markFailed(String error) {
        this.attempts++;
        this.lastError = error == null ? null : error.substring(0, Math.min(500, error.length()));
    }

    public String getEventId() {
        return eventId;
    }

    public String getExchange() {
        return exchange;
    }

    public String getRoutingKey() {
        return routingKey;
    }

    public String getPayload() {
        return payload;
    }

    public Instant getPublishedAt() {
        return publishedAt;
    }

    public int getAttempts() {
        return attempts;
    }

    public String getLastError() {
        return lastError;
    }
}
