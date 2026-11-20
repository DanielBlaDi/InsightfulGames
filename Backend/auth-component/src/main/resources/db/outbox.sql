-- Outbox de eventos de Auth. Lo ejecuta Auth al arrancar (spring.sql.init), así también se crea
-- en volúmenes de MySQL que ya existían. Es idempotente.
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id      VARCHAR(36)  NOT NULL,
    exchange_name VARCHAR(100) NOT NULL,
    routing_key   VARCHAR(100) NOT NULL,
    payload       TEXT         NOT NULL,
    created_at    TIMESTAMP(6) NOT NULL,
    published_at  TIMESTAMP(6) NULL,
    attempts      INT          NOT NULL DEFAULT 0,
    last_error    VARCHAR(500) NULL,
    PRIMARY KEY (event_id),
    INDEX idx_outbox_pending (published_at, created_at)
);
