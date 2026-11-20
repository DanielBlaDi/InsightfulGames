package com.prototipo.auth.controller;

import com.prototipo.auth.dto.LoginRequest;
import com.prototipo.auth.dto.LoginResponse;
import com.prototipo.auth.dto.RegisterRequest;
import com.prototipo.auth.dto.RegisterResponse;
import com.prototipo.auth.service.AuthService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Rutas de Auth. v9 (sección 7) las publica como /internal/auth/*, siempre a través del gateway.
 * /auth/* se mantiene mientras el gateway actual siga llamando a esas rutas.
 */
@RestController
@RequestMapping({"/internal/auth", "/auth"})
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/register")
    public ResponseEntity<RegisterResponse> registrar(
            @Valid @RequestBody RegisterRequest solicitud) {

        RegisterResponse respuesta = authService.registrar(solicitud);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(respuesta);
    }

    @PostMapping("/login")
    public ResponseEntity<LoginResponse> iniciarSesion(
            @Valid @RequestBody LoginRequest solicitud) {

        return ResponseEntity.ok(
                authService.iniciarSesion(solicitud)
        );
    }

    @DeleteMapping("/account")
    public ResponseEntity<Void> eliminarCuenta(
            @RequestHeader(value = "X-User-Id", required = false)
            String userId) {

        authService.eliminarCuenta(userId);

        return ResponseEntity.noContent().build();
    }
}