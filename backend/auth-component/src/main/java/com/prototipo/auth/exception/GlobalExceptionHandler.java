package com.prototipo.auth.exception;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.util.Map;

/** Todos los errores con el formato común del contrato v9 (sección 1). */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, Object>> manejarApi(ApiException excepcion) {
        return error(excepcion.status(), excepcion.code(), excepcion.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> manejarValidacion(MethodArgumentNotValidException excepcion) {
        String detalle = excepcion.getBindingResult()
                .getFieldErrors()
                .stream()
                .findFirst()
                .map(error -> error.getDefaultMessage())
                .orElse("Los datos enviados no son válidos");
        return error(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", detalle);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, Object>> manejarSolicitudIncorrecta(HttpMessageNotReadableException excepcion) {
        return error(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", "El cuerpo de la solicitud no es válido");
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<Map<String, Object>> manejarIntegridad(DataIntegrityViolationException excepcion) {
        ApiException conflicto = ApiException.usernameTaken();
        return error(conflicto.status(), conflicto.code(), conflicto.getMessage());
    }

    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<Map<String, Object>> manejarRutaInexistente(NoResourceFoundException excepcion) {
        return error(HttpStatus.NOT_FOUND, "NOT_FOUND", "Ruta inexistente");
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> manejarInesperado(Exception excepcion) {
        log.error("Error inesperado", excepcion);
        return error(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "Error interno del servidor");
    }

    private static ResponseEntity<Map<String, Object>> error(HttpStatus estado, String codigo, String mensaje) {
        return ResponseEntity.status(estado).body(Map.of("error", Map.of("code", codigo, "message", mensaje)));
    }
}
