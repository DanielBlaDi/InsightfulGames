package com.prototipo.auth.security;

import com.prototipo.auth.entity.User;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;

@Service
public class JwtService {

    private static final long DURACION_TOKEN_MS = 3_600_000L;

    private final SecretKey clave;

    public JwtService(@Value("${JWT_SECRET}") String secreto) {
        byte[] bytes = secreto.getBytes(StandardCharsets.UTF_8);

        if (bytes.length < 32) {
            throw new IllegalArgumentException(
                    "JWT_SECRET debe tener al menos 32 bytes"
            );
        }

        this.clave = Keys.hmacShaKeyFor(bytes);
    }

    public String generarToken(User usuario) {
        Date ahora = new Date();
        Date expiracion = new Date(ahora.getTime() + DURACION_TOKEN_MS);

        return Jwts.builder()
                .subject(usuario.getUserId())
                .claim("username", usuario.getUsername())
                .issuedAt(ahora)
                .expiration(expiracion)
                .signWith(clave, Jwts.SIG.HS256)
                .compact();
    }

    public Claims validarToken(String token) {
        return Jwts.parser()
                .verifyWith(clave)
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    public long getDuracionSegundos() {
        return DURACION_TOKEN_MS / 1000;
    }
}