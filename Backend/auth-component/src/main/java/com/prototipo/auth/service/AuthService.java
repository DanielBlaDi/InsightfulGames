package com.prototipo.auth.service;

import com.prototipo.auth.dto.LoginRequest;
import com.prototipo.auth.dto.LoginResponse;
import com.prototipo.auth.dto.RegisterRequest;
import com.prototipo.auth.dto.RegisterResponse;
import com.prototipo.auth.dto.UserResponse;
import com.prototipo.auth.entity.User;
import com.prototipo.auth.repository.UserRepository;
import com.prototipo.auth.security.JwtService;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AuthService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;

    public AuthService(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            JwtService jwtService) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
    }

    @Transactional
    public RegisterResponse registrar(RegisterRequest solicitud) {
        if (userRepository.existsByUsername(solicitud.username())) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "USERNAME_TAKEN"
            );
        }

        String hash = passwordEncoder.encode(solicitud.password());
        User usuario = new User(solicitud.username(), hash);

        try {
            User guardado = userRepository.saveAndFlush(usuario);

            return new RegisterResponse(
                    guardado.getUserId(),
                    guardado.getUsername()
            );
        } catch (DataIntegrityViolationException excepcion) {
            // También contempla dos registros simultáneos con el mismo usuario.
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "USERNAME_TAKEN"
            );
        }
    }

    @Transactional(readOnly = true)
    public LoginResponse iniciarSesion(LoginRequest solicitud) {
        User usuario = userRepository
                .findByUsername(solicitud.username())
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS"
                ));

        if (!passwordEncoder.matches(
                solicitud.password(), usuario.getPasswordHash())) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS"
            );
        }

        String token = jwtService.generarToken(usuario);

        return new LoginResponse(
                token,
                jwtService.getDuracionSegundos(),
                new UserResponse(usuario.getUserId(), usuario.getUsername())
        );
    }

    @Transactional
    public void eliminarCuenta(String userId) {
        if (userId == null || userId.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "VALIDATION_ERROR"
            );
        }

        User usuario = userRepository.findById(userId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "USER_NOT_FOUND"
                ));

        userRepository.delete(usuario);
    }
}