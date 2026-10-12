package com.chess.gameservice.error;

import org.springframework.http.HttpStatus;

/** Error con la forma del contrato: { "error": { "code": "...", "message": "..." } }. */
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

    public static ApiException unauthorized() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED", "Falta la cabecera X-User-Id");
    }

    public static ApiException gameNotFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "GAME_NOT_FOUND", "La partida no existe o no te pertenece");
    }

    public static ApiException unavailable(String message) {
        return new ApiException(HttpStatus.BAD_GATEWAY, "SERVICE_UNAVAILABLE", message);
    }
}
