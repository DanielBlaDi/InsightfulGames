package com.prototipo.auth;

import com.prototipo.auth.deletion.AccountDeletionClient;
import com.prototipo.auth.deletion.AccountDeletionClient.Dependency;
import com.prototipo.auth.entity.User;
import com.prototipo.auth.outbox.EventSender;
import com.prototipo.auth.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.InOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Auditoría del borrado coordinado (sección 7): fallos en cada dependencia, reintentos y carreras.
 * Los servicios se simulan con un registro de llamadas; MySQL es H2 en modo MySQL.
 */
@SpringBootTest
@ActiveProfiles("test")
class AccountDeletionTest {

    private static final Dependency GAME_LOGIC = AccountDeletionClient.DEPENDENCIES.get(0);
    private static final Dependency TUTOR = AccountDeletionClient.DEPENDENCIES.get(1);
    private static final Dependency PROFILE = AccountDeletionClient.DEPENDENCIES.get(2);

    @Autowired private WebApplicationContext context;
    @MockitoSpyBean private UserRepository users;
    @MockitoBean private AccountDeletionClient deletion;
    @MockitoBean private EventSender sender;

    private MockMvc mvc;
    private String userId;
    /** Orden real de las llamadas a los servicios, acumulado entre intentos. */
    private final List<String> calls = new ArrayList<>();

    @BeforeEach
    void setUp() {
        reset(users, deletion);
        users.deleteAllInBatch();
        userId = users.save(new User("ana", "hash")).getUserId();
        calls.clear();
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    /** Cada dependencia responde según la lista de las que fallan; las demás dan 204. */
    private void servicesFailing(Dependency... failing) {
        List<Dependency> down = List.of(failing);
        when(deletion.delete(any(Dependency.class), eq(userId))).thenAnswer(inv -> {
            Dependency d = inv.getArgument(0);
            calls.add(d.name());
            return !down.contains(d);
        });
    }

    private ResultActions deleteAccount() throws Exception {
        return mvc.perform(delete("/internal/auth/account").header("X-User-Id", userId));
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 1, 2})
    void aFailingDependencyStopsTheChainAndKeepsTheUser(int failingIndex) throws Exception {
        Dependency failing = AccountDeletionClient.DEPENDENCIES.get(failingIndex);
        servicesFailing(failing);

        deleteAccount()
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error.code").value("SERVICES_UNAVAILABLE"))
                .andExpect(jsonPath("$.error.message").value(org.hamcrest.Matchers.containsString(failing.name())));

        // Se llamó hasta la que falló, en orden, y ninguna posterior.
        List<String> expected = AccountDeletionClient.DEPENDENCIES.subList(0, failingIndex + 1)
                .stream().map(Dependency::name).toList();
        assertThat(calls).containsExactlyElementsOf(expected);
        assertThat(users.existsById(userId)).isTrue();
    }

    @Test
    void retryAfterGameLogicAlreadyDeletedRepeatsTheWholeChainSafely() throws Exception {
        // Primer intento: Game Logic ya anonimizó, Tutor cae.
        servicesFailing(TUTOR);
        deleteAccount().andExpect(status().isServiceUnavailable());
        assertThat(users.existsById(userId)).isTrue();

        // Segundo intento: Profile/Stats cae.
        servicesFailing(PROFILE);
        deleteAccount().andExpect(status().isServiceUnavailable());
        assertThat(users.existsById(userId)).isTrue();

        // Tercer intento: todo responde.
        servicesFailing();
        deleteAccount().andExpect(status().isNoContent());

        assertThat(calls).containsExactly(
                "Game Logic", "Tutor",
                "Game Logic", "Tutor", "Profile/Stats",
                "Game Logic", "Tutor", "Profile/Stats");
        assertThat(users.existsById(userId)).isFalse();
    }

    @Test
    void successDeletesTheUserOnlyAfterTheThreeConfirmations() throws Exception {
        servicesFailing();

        deleteAccount().andExpect(status().isNoContent());

        InOrder order = inOrder(deletion, users);
        order.verify(deletion).delete(GAME_LOGIC, userId);
        order.verify(deletion).delete(TUTOR, userId);
        order.verify(deletion).delete(PROFILE, userId);
        order.verify(users).deleteById(userId);
        assertThat(users.existsById(userId)).isFalse();
    }

    @Test
    void repeatingASuccessfulDeletionIsA204WithoutCallingAnyone() throws Exception {
        servicesFailing();
        deleteAccount().andExpect(status().isNoContent());
        calls.clear();

        deleteAccount().andExpect(status().isNoContent());

        assertThat(calls).isEmpty();
    }

    @Test
    void concurrentDeletionThatFinishesFirstDoesNotBreakTheSecond() throws Exception {
        // Mientras este borrado espera a Profile/Stats, otro borrado de la misma cuenta termina.
        when(deletion.delete(any(Dependency.class), eq(userId))).thenReturn(true);
        doAnswer(inv -> {
            users.deleteAllInBatch();
            return true;
        }).when(deletion).delete(PROFILE, userId);

        deleteAccount().andExpect(status().isNoContent());

        assertThat(users.existsById(userId)).isFalse();
    }

    @Test
    void mysqlFailureAfterTheThreeConfirmationsIsRetryable() throws Exception {
        servicesFailing();
        doThrow(new DataAccessResourceFailureException("MySQL no responde")).when(users).deleteById(userId);

        deleteAccount()
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.error.code").value("INTERNAL_ERROR"));
        assertThat(users.existsById(userId)).isTrue();

        reset(users); // el espía vuelve a llamar al repositorio real
        deleteAccount().andExpect(status().isNoContent());
        assertThat(users.existsById(userId)).isFalse();
    }

    @Test
    void missingHeaderNeverReachesTheServices() throws Exception {
        mvc.perform(delete("/internal/auth/account"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
        mvc.perform(delete("/internal/auth/account").header("X-User-Id", "  "))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(deletion);
        verify(users, org.mockito.Mockito.never()).deleteById(any());
    }
}
