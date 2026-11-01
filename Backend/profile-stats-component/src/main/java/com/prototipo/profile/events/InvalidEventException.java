package com.prototipo.profile.events;

/** Mensaje que no cumple el contrato. Reintentarlo no lo arregla: va directo a la .dlq. */
public class InvalidEventException extends RuntimeException {

    public InvalidEventException(String message) {
        super(message);
    }

    public InvalidEventException(String message, Throwable cause) {
        super(message, cause);
    }
}
