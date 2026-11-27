package com.prototipo.auth.dto;

public record LoginResponse(
        String accessToken,
        long expiresIn,
        UserResponse user
) {}
