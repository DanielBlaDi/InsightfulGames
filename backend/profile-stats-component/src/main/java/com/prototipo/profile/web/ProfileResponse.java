package com.prototipo.profile.web;

/** GET /profile/me. createdAt en ISO 8601 UTC. */
public record ProfileResponse(String userId, String username, String createdAt) {
}
