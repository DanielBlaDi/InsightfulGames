package com.prototipo.profile.web;

import org.springframework.http.HttpStatus;

/** Error con la forma común del contrato: { "error": { "code", "message" } }. */
public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final String code;

    public ApiException(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public HttpStatus status() {
        return status;
    }

    public String code() {
        return code;
    }

    public static ApiException validation(String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", message);
    }

    /**
     * Perfil inexistente. v9 no define este código: el perfil solo nace con user.registered
     * porque la ruta interna no trae el username (pendiente de cerrar en el contrato).
     */
    public static ApiException profileNotFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "PROFILE_NOT_FOUND", "El perfil no existe");
    }
}
