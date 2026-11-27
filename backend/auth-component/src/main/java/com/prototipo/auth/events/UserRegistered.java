package com.prototipo.auth.events;

/** Evento de aplicación: un usuario se registró. El mensaje para RabbitMQ va por el outbox. */
public record UserRegistered(String userId, String username) {
}
