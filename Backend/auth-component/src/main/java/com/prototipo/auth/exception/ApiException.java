package com.prototipo.auth.exception;

import org.springframework.http.HttpStatus;

/** Error con la forma común del contrato v9: { "error": { "code", "message" } }. */
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

    public static ApiException usernameTaken() {
        return new ApiException(HttpStatus.CONFLICT, "USERNAME_TAKEN", "El nombre de usuario ya existe");
    }

    public static ApiException invalidCredentials() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS", "Usuario o contraseña incorrectos");
    }

    public static ApiException servicesUnavailable(String service) {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "SERVICES_UNAVAILABLE",
                "No se pudo borrar la cuenta: " + service + " no respondió. Intenta de nuevo");
    }
}
