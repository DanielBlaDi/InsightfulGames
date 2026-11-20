package com.prototipo.auth.service;

import com.prototipo.auth.deletion.AccountDeletionClient;
import com.prototipo.auth.deletion.AccountDeletionClient.Dependency;
import com.prototipo.auth.dto.LoginRequest;
import com.prototipo.auth.dto.LoginResponse;
import com.prototipo.auth.dto.RegisterRequest;
import com.prototipo.auth.dto.RegisterResponse;
import com.prototipo.auth.dto.UserResponse;
import com.prototipo.auth.entity.User;
import com.prototipo.auth.events.UserRegistered;
import com.prototipo.auth.exception.ApiException;
import com.prototipo.auth.outbox.UserRegisteredOutbox;
import com.prototipo.auth.repository.UserRepository;
import com.prototipo.auth.security.JwtService;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final ApplicationEventPublisher events;
    private final AccountDeletionClient deletionClient;
    private final UserRegisteredOutbox outbox;

    public AuthService(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            JwtService jwtService,
            ApplicationEventPublisher events,
            AccountDeletionClient deletionClient,
            UserRegisteredOutbox outbox) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.events = events;
        this.deletionClient = deletionClient;
        this.outbox = outbox;
    }

    /**
     * Registra al usuario y guarda user.registered en el outbox en la misma transacción: o quedan
     * los dos o ninguno. El evento se publica después, aunque RabbitMQ esté caído al registrar.
     */
    @Transactional
    public RegisterResponse registrar(RegisterRequest solicitud) {
        if (userRepository.existsByUsername(solicitud.username())) {
            throw ApiException.usernameTaken();
        }

        String hash = passwordEncoder.encode(solicitud.password());
        User usuario = new User(solicitud.username(), hash);

        try {
            User guardado = userRepository.saveAndFlush(usuario);
            UserRegistered registrado = new UserRegistered(guardado.getUserId(), guardado.getUsername());
            outbox.record(registrado);
            events.publishEvent(registrado); // avisa al publicador cuando la transacción se confirme
            return new RegisterResponse(
                    guardado.getUserId(),
                    guardado.getUsername()
            );
        } catch (DataIntegrityViolationException excepcion) {
            // También contempla dos registros simultáneos con el mismo usuario.
            throw ApiException.usernameTaken();
        }
    }

    @Transactional(readOnly = true)
    public LoginResponse iniciarSesion(LoginRequest solicitud) {
        User usuario = userRepository
                .findByUsername(solicitud.username())
                .orElseThrow(ApiException::invalidCredentials);

        if (!passwordEncoder.matches(
                solicitud.password(), usuario.getPasswordHash())) {
            throw ApiException.invalidCredentials();
        }

        String token = jwtService.generarToken(usuario);

        return new LoginResponse(
                token,
                jwtService.getDuracionSegundos(),
                new UserResponse(usuario.getUserId(), usuario.getUsername())
        );
    }

    /**
     * Borrado coordinado (sección 7): Game Logic, Tutor y Profile/Stats, en ese orden. La fila de
     * MySQL se borra solo si los tres respondieron 204; si uno falla, no se borra nada aquí y el
     * usuario puede reintentar, porque las tres rutas son idempotentes. Sin transacción: no se
     * mantiene abierta una conexión a MySQL mientras se espera a otros servicios.
     */
    public void eliminarCuenta(String userId) {
        if (userId == null || userId.isBlank()) {
            throw ApiException.validation("Falta la cabecera X-User-Id");
        }
        // La fila desaparece solo al final de un borrado completo: si ya no está, no queda nada por hacer.
        if (!userRepository.existsById(userId)) {
            return;
        }

        for (Dependency dependencia : AccountDeletionClient.DEPENDENCIES) {
            if (!deletionClient.delete(dependencia, userId)) {
                throw ApiException.servicesUnavailable(dependencia.name());
            }
        }

        userRepository.deleteById(userId);
    }
}
