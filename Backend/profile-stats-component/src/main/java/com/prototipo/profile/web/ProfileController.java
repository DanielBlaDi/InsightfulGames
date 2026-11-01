package com.prototipo.profile.web;

import com.prototipo.profile.service.ProfileService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Rutas internas de la sección 8. El gateway las llama con el userId tomado del JWT;
 * Auth llama al DELETE durante el borrado de cuenta.
 */
@RestController
public class ProfileController {

    private final ProfileService service;

    public ProfileController(ProfileService service) {
        this.service = service;
    }

    @GetMapping("/internal/profile/users/{userId}/profile")
    public ProfileResponse profile(@PathVariable String userId) {
        return service.getProfile(userId);
    }

    @GetMapping("/internal/profile/users/{userId}/stats")
    public StatsResponse stats(@PathVariable String userId) {
        return service.getStats(userId);
    }

    @DeleteMapping("/internal/profile/users/{userId}")
    public ResponseEntity<Void> delete(@PathVariable String userId) {
        service.deleteUser(userId);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
