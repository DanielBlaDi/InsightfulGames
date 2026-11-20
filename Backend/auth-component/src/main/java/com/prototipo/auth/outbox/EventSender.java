package com.prototipo.auth.outbox;

/** Publica un evento y solo vuelve cuando el broker lo confirmó. Si no, lanza una excepción. */
public interface EventSender {

    void send(OutboxEvent event);
}
