package com.prototipo.auth;

import com.prototipo.auth.entity.User;
import com.prototipo.auth.outbox.EventSender;
import com.prototipo.auth.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
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

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Borrado de cuenta en Auth (sección 7): solo la fila de MySQL (H2 en modo MySQL). La orquestación
 * con Game Logic, Tutor y Profile/Stats la hace el gateway; Auth ya no llama a nadie.
 */
@SpringBootTest
@ActiveProfiles("test")
class AccountDeletionTest {

    @Autowired private WebApplicationContext context;
    @MockitoSpyBean private UserRepository users;
    @MockitoBean private EventSender sender;

    private MockMvc mvc;
    private String userId;

    @BeforeEach
    void setUp() {
        reset(users);
        users.deleteAllInBatch();
        userId = users.save(new User("ana", "hash")).getUserId();
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    private ResultActions deleteAccount() throws Exception {
        return mvc.perform(delete("/internal/auth/account").header("X-User-Id", userId));
    }

    @Test
    void deletesTheRowAndRespondsNoContent() throws Exception {
        deleteAccount().andExpect(status().isNoContent());

        assertThat(users.existsById(userId)).isFalse();
    }

    @Test
    void repeatingTheDeletionIsANoContentThatDoesNotTouchTheRepositoryAgain() throws Exception {
        deleteAccount().andExpect(status().isNoContent());
        reset(users);

        deleteAccount().andExpect(status().isNoContent());

        verify(users, never()).deleteById(any());
    }

    @Test
    void mysqlFailureIsRetryable() throws Exception {
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
    void missingHeaderNeverTouchesTheRepository() throws Exception {
        mvc.perform(delete("/internal/auth/account"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
        mvc.perform(delete("/internal/auth/account").header("X-User-Id", "  "))
                .andExpect(status().isBadRequest());
        verify(users, never()).deleteById(any());
        assertThat(users.existsById(userId)).isTrue();
    }

    @Test
    void existenceEndpointReturnsTheUserWhileItExists() throws Exception {
        mvc.perform(get("/internal/auth/users/" + userId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value(userId))
                .andExpect(jsonPath("$.username").value("ana"));
    }

    @Test
    void existenceEndpointIs404AfterTheDeletion() throws Exception {
        deleteAccount().andExpect(status().isNoContent());

        mvc.perform(get("/internal/auth/users/" + userId))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("USER_NOT_FOUND"));
    }
}
