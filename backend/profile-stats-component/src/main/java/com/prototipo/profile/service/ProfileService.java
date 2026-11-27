package com.prototipo.profile.service;

import com.prototipo.profile.domain.DeletedUser;
import com.prototipo.profile.domain.DeletedUserRepository;
import com.prototipo.profile.domain.ProfileRepository;
import com.prototipo.profile.domain.StatsRepository;
import com.prototipo.profile.web.ApiException;
import com.prototipo.profile.web.ProfileResponse;
import com.prototipo.profile.web.StatsResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;

@Service
public class ProfileService {

    private final ProfileRepository profiles;
    private final StatsRepository stats;
    private final DeletedUserRepository deletedUsers;
    private final Clock clock;

    public ProfileService(ProfileRepository profiles, StatsRepository stats,
                          DeletedUserRepository deletedUsers, Clock clock) {
        this.profiles = profiles;
        this.stats = stats;
        this.deletedUsers = deletedUsers;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public ProfileResponse getProfile(String userId) {
        requireUuid(userId);
        return profiles.findById(userId)
                .map(p -> new ProfileResponse(p.getUserId(), p.getUsername(), p.getCreatedAt().toString()))
                .orElseThrow(ApiException::profileNotFound);
    }

    /** Sin perfil o sin partidas, contadores en cero. Leer nunca crea filas. */
    @Transactional(readOnly = true)
    public StatsResponse getStats(String userId) {
        requireUuid(userId);
        return stats.findById(userId)
                .map(s -> new StatsResponse(s.getGamesPlayed(), s.getWins(), s.getLosses(), s.getDraws()))
                .orElse(StatsResponse.EMPTY);
    }

    /**
     * Borra perfil y contadores, y recuerda el borrado para no recrear el perfil con eventos
     * tardíos. Idempotente: responde igual aunque el usuario no exista o ya se haya borrado.
     */
    @Transactional
    public void deleteUser(String userId) {
        requireUuid(userId);
        stats.deleteById(userId);
        profiles.deleteById(userId);
        if (!deletedUsers.existsById(userId)) {
            deletedUsers.save(new DeletedUser(userId, Instant.now(clock)));
        }
    }

    private static void requireUuid(String userId) {
        if (!Ids.isUuid(userId)) {
            throw ApiException.validation("userId debe ser un UUID");
        }
    }
}
