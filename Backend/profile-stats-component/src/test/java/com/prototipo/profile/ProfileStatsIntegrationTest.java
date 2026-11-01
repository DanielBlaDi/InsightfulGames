package com.prototipo.profile;

import com.prototipo.profile.domain.DeletedUserRepository;
import com.prototipo.profile.domain.ProcessedEventRepository;
import com.prototipo.profile.domain.ProfileRepository;
import com.prototipo.profile.domain.StatsRepository;
import com.prototipo.profile.events.EventParser;
import com.prototipo.profile.events.EventProcessor;
import com.prototipo.profile.events.EventProcessor.Outcome;
import com.prototipo.profile.events.GameFinishedEvent;
import com.prototipo.profile.events.GameFinishedEvent.Participant;
import com.prototipo.profile.events.UserRegisteredEvent;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Servicio completo sobre H2 (modo PostgreSQL) con el script real de Databases/profile. */
@SpringBootTest
@ActiveProfiles("test")
class ProfileStatsIntegrationTest {

    private static final String ANA = "11111111-1111-4111-8111-111111111111";
    private static final String BEA = "22222222-2222-4222-8222-222222222222";
    private static final String ANONYMOUS = "00000000-0000-0000-0000-000000000000";

    @Autowired private WebApplicationContext context;
    @Autowired private EventProcessor processor;
    @Autowired private EventParser parser;
    @Autowired private ProfileRepository profiles;
    @Autowired private StatsRepository stats;
    @Autowired private ProcessedEventRepository processed;
    @Autowired private DeletedUserRepository deletedUsers;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        stats.deleteAllInBatch();
        profiles.deleteAllInBatch();
        processed.deleteAllInBatch();
        deletedUsers.deleteAllInBatch();
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    private static String id() {
        return UUID.randomUUID().toString();
    }

    private static UserRegisteredEvent registered(String userId, String username) {
        return new UserRegisteredEvent(id(), "user.registered", "2026-10-29T15:00:00Z", userId, username);
    }

    private static GameFinishedEvent finished(String mode, String result, String endReason, Participant... ps) {
        return new GameFinishedEvent(id(), "game.finished", "2026-10-29T15:20:00Z", id(),
                "multiplayer".equals(mode) ? id() : null, mode, List.of(ps), result, endReason,
                "2026-10-29T15:20:00Z");
    }

    private static Participant white(String userId) {
        return new Participant(userId, "white");
    }

    private static Participant black(String userId) {
        return new Participant(userId, "black");
    }

    private void expectStats(String userId, int played, int wins, int losses, int draws) throws Exception {
        mvc.perform(get("/internal/profile/users/{id}/stats", userId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.gamesPlayed").value(played))
                .andExpect(jsonPath("$.wins").value(wins))
                .andExpect(jsonPath("$.losses").value(losses))
                .andExpect(jsonPath("$.draws").value(draws));
    }

    @Test
    void userRegisteredCreatesProfileAndZeroStats() throws Exception {
        assertThat(processor.userRegistered(registered(ANA, "ana"))).isEqualTo(Outcome.APPLIED);

        mvc.perform(get("/internal/profile/users/{id}/profile", ANA))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(ANA))
                .andExpect(jsonPath("$.username").value("ana"))
                .andExpect(jsonPath("$.createdAt").value("2026-10-29T15:00:00Z"));
        expectStats(ANA, 0, 0, 0, 0);
    }

    @Test
    void repeatedUserRegisteredIsIgnored() {
        UserRegisteredEvent event = registered(ANA, "ana");
        processor.userRegistered(event);

        assertThat(processor.userRegistered(event)).isEqualTo(Outcome.DUPLICATE);
        assertThat(profiles.count()).isEqualTo(1);
    }

    @Test
    void multiplayerResultsAreCounted() throws Exception {
        processor.userRegistered(registered(ANA, "ana"));
        processor.userRegistered(registered(BEA, "bea"));

        processor.gameFinished(finished("multiplayer", "white", "checkmate", white(ANA), black(BEA)));
        processor.gameFinished(finished("multiplayer", "draw", "draw", white(ANA), black(BEA)));
        processor.gameFinished(finished("multiplayer", "white", "surrender", white(BEA), black(ANA)));

        expectStats(ANA, 3, 1, 1, 1);
        expectStats(BEA, 3, 1, 1, 1);
    }

    @Test
    void repeatedGameFinishedCountsOnce() throws Exception {
        processor.userRegistered(registered(ANA, "ana"));
        processor.userRegistered(registered(BEA, "bea"));
        GameFinishedEvent event = finished("multiplayer", "black", "timeout", white(ANA), black(BEA));

        assertThat(processor.gameFinished(event)).isEqualTo(Outcome.APPLIED);
        assertThat(processor.gameFinished(event)).isEqualTo(Outcome.DUPLICATE);

        expectStats(ANA, 1, 0, 1, 0);
        expectStats(BEA, 1, 1, 0, 0);
    }

    @Test
    void onlyMultiplayerGamesWithResultCount() throws Exception {
        processor.userRegistered(registered(ANA, "ana"));
        processor.userRegistered(registered(BEA, "bea"));

        List<GameFinishedEvent> ignored = List.of(
                finished("local", "white", "checkmate", white(ANA), black(ANA)),
                finished("vs_bot", "black", "checkmate", white(ANA)),
                finished("multiplayer", null, "expired", white(ANA)),
                finished("multiplayer", "white", "expired", white(ANA), black(BEA)));
        for (GameFinishedEvent event : ignored) {
            assertThat(processor.gameFinished(event)).isEqualTo(Outcome.IGNORED);
        }

        expectStats(ANA, 0, 0, 0, 0);
        assertThat(processed.count()).isEqualTo(2 + ignored.size());
    }

    @Test
    void participantsWithoutProfileAreIgnored() throws Exception {
        processor.userRegistered(registered(ANA, "ana"));
        String stranger = id();

        processor.gameFinished(finished("multiplayer", "white", "checkmate", white(ANA), black(stranger)));
        processor.gameFinished(finished("multiplayer", "black", "abandonment", white(ANONYMOUS), black(ANA)));

        expectStats(ANA, 2, 2, 0, 0);
        assertThat(stats.existsById(stranger)).isFalse();
        assertThat(profiles.existsById(stranger)).isFalse();
        assertThat(stats.existsById(ANONYMOUS)).isFalse();
    }

    @Test
    void failedTransactionLeavesNothingCounted() {
        processor.userRegistered(registered(ANA, "ana"));
        processor.userRegistered(registered(BEA, "bea"));
        // El eventId no cabe en la columna: el registro del evento falla al confirmar y la
        // suma hecha antes en la misma transacción también se deshace.
        GameFinishedEvent tooLong = new GameFinishedEvent("x".repeat(40), "game.finished", null, id(), id(),
                "multiplayer", List.of(white(ANA), black(BEA)), "white", "checkmate", null);

        assertThatThrownBy(() -> processor.gameFinished(tooLong)).isInstanceOf(RuntimeException.class);

        assertThat(stats.findById(ANA).orElseThrow().getGamesPlayed()).isZero();
        assertThat(stats.findById(BEA).orElseThrow().getGamesPlayed()).isZero();
    }

    @Test
    void deleteIsIdempotentAndHidesTheProfile() throws Exception {
        processor.userRegistered(registered(ANA, "ana"));

        mvc.perform(delete("/internal/profile/users/{id}", ANA)).andExpect(status().isNoContent());
        mvc.perform(delete("/internal/profile/users/{id}", ANA)).andExpect(status().isNoContent());
        mvc.perform(delete("/internal/profile/users/{id}", id())).andExpect(status().isNoContent());

        mvc.perform(get("/internal/profile/users/{id}/profile", ANA))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("PROFILE_NOT_FOUND"))
                .andExpect(jsonPath("$.error.message").isString());
        expectStats(ANA, 0, 0, 0, 0);
    }

    @Test
    void lateEventsDoNotRecreateADeletedProfile() throws Exception {
        UserRegisteredEvent late = registered(BEA, "bea");
        processor.userRegistered(registered(ANA, "ana"));
        mvc.perform(delete("/internal/profile/users/{id}", BEA)).andExpect(status().isNoContent());

        assertThat(processor.userRegistered(late)).isEqualTo(Outcome.IGNORED);
        processor.gameFinished(finished("multiplayer", "white", "checkmate", white(ANA), black(BEA)));

        assertThat(profiles.existsById(BEA)).isFalse();
        assertThat(stats.existsById(BEA)).isFalse();
        expectStats(ANA, 1, 1, 0, 0);
    }

    @Test
    void readingDoesNotCreateRows() throws Exception {
        mvc.perform(get("/internal/profile/users/{id}/profile", ANA)).andExpect(status().isNotFound());
        expectStats(ANA, 0, 0, 0, 0);

        assertThat(profiles.count()).isZero();
        assertThat(stats.count()).isZero();
    }

    @Test
    void invalidUserIdIsAValidationError() throws Exception {
        mvc.perform(get("/internal/profile/users/{id}/stats", "no-es-uuid"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
        mvc.perform(delete("/internal/profile/users/{id}", "no-es-uuid"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void healthResponds() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void parsesTheContractJson() {
        String json = """
                {"eventId":"%s","eventType":"game.finished","occurredAt":"2026-10-29T15:20:00Z",
                 "gameId":"%s","matchId":"%s","mode":"multiplayer",
                 "participants":[{"userId":"%s","color":"white"},{"userId":"%s","color":"black"}],
                 "result":"white","endReason":"checkmate","finishedAt":"2026-10-29T15:20:00Z","extra":1}
                """.formatted(id(), id(), id(), ANA, BEA);

        GameFinishedEvent event = parser.gameFinished(json.getBytes(StandardCharsets.UTF_8));

        assertThat(event.participants()).containsExactly(white(ANA), black(BEA));
        assertThat(event.result()).isEqualTo("white");
    }
}
