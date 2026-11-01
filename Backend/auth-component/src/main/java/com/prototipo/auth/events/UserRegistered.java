package com.prototipo.auth.events;

/** Evento de aplicación: un usuario se registró. Se publica en RabbitMQ al confirmar la transacción. */
public record UserRegistered(String userId, String username) {
}
