package com.prototipo.auth;

import com.prototipo.auth.deletion.AccountDeletionClient;
import com.prototipo.auth.deletion.AccountDeletionClient.Dependency;
import com.prototipo.auth.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Auth completo sobre H2 (modo MySQL). RabbitMQ y los servicios del borrado se simulan. */
@SpringBootTest
@ActiveProfiles("test")
class AuthIntegrationTest {

    @Autowired private WebApplicationContext context;
    @Autowired private UserRepository users;
    @Autowired private JsonMapper mapper;

    @MockitoBean private RabbitTemplate rabbit;
    @MockitoBean private AccountDeletionClient deletion;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        users.deleteAllInBatch();
        reset(rabbit, deletion);
        mvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    private String register(String path, String username) throws Exception {
        String body = mvc.perform(post(path).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"%s\",\"password\":\"claveSegura123\"}".formatted(username)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.username").value(username))
                .andReturn().getResponse().getContentAsString();
        return mapper.readTree(body).get("userId").asString();
    }

    @Test
    void registerPublishesUserRegisteredAfterCommit() throws Exception {
        String userId = register("/internal/auth/register", "ana");

        ArgumentCaptor<Message> sent = ArgumentCaptor.forClass(Message.class);
        verify(rabbit).send(eq("user.events"), eq("user.registered"), sent.capture());
        JsonNode event = mapper.readTree(sent.getValue().getBody());
        assertThat(event.get("eventType").asString()).isEqualTo("user.registered");
        assertThat(event.get("userId").asString()).isEqualTo(userId);
        assertThat(event.get("username").asString()).isEqualTo("ana");
        assertThat(event.get("eventId").asString()).matches("[0-9a-f-]{36}");
        assertThat(event.get("occurredAt").asString()).endsWith("Z");
        assertThat(sent.getValue().getMessageProperties().getContentType()).isEqualTo("application/json");
    }

    @Test
    void duplicateUsernameIsAConflictAndPublishesNothing() throws Exception {
        register("/internal/auth/register", "ana");
        reset(rabbit);

        mvc.perform(post("/internal/auth/register").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"ana\",\"password\":\"otraClave123\"}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("USERNAME_TAKEN"))
                .andExpect(jsonPath("$.error.message").isString());
        verifyNoInteractions(rabbit);
    }

    @Test
    void registrationSurvivesARabbitOutage() throws Exception {
        org.mockito.Mockito.doThrow(new org.springframework.amqp.AmqpConnectException(new java.net.ConnectException()))
                .when(rabbit).send(anyString(), anyString(), any(Message.class));

        String userId = register("/internal/auth/register", "bea");

        assertThat(users.existsById(userId)).isTrue();
        verify(rabbit, times(3)).send(anyString(), anyString(), any(Message.class));
    }

    @Test
    void validationErrorsUseTheCommonFormat() throws Exception {
        mvc.perform(post("/internal/auth/register").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"an\",\"password\":\"claveSegura123\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.error.message").isString());
    }

    @Test
    void loginReturnsTokenAndRejectsBadCredentials() throws Exception {
        String userId = register("/internal/auth/register", "ana");

        mvc.perform(post("/internal/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"ana\",\"password\":\"claveSegura123\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").isString())
                .andExpect(jsonPath("$.expiresIn").value(3600))
                .andExpect(jsonPath("$.user.userId").value(userId));

        mvc.perform(post("/internal/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"ana\",\"password\":\"incorrecta\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("INVALID_CREDENTIALS"));
    }

    @Test
    void legacyRoutesKeepWorkingForTheCurrentGateway() throws Exception {
        register("/auth/register", "ana");

        mvc.perform(post("/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"ana\",\"password\":\"claveSegura123\"}"))
                .andExpect(status().isOk());
    }

    @Test
    void deleteCallsTheThreeServicesInOrderAndThenRemovesTheUser() throws Exception {
        String userId = register("/internal/auth/register", "ana");
        when(deletion.delete(any(Dependency.class), eq(userId))).thenReturn(true);

        mvc.perform(delete("/internal/auth/account").header("X-User-Id", userId))
                .andExpect(status().isNoContent());

        InOrder order = inOrder(deletion);
        for (Dependency dependency : AccountDeletionClient.DEPENDENCIES) {
            order.verify(deletion).delete(dependency, userId);
        }
        assertThat(users.existsById(userId)).isFalse();
    }

    @Test
    void deleteStopsAt503AndKeepsTheUserWhenADependencyFails() throws Exception {
        String userId = register("/internal/auth/register", "ana");
        Dependency gameLogic = AccountDeletionClient.DEPENDENCIES.get(0);
        Dependency tutor = AccountDeletionClient.DEPENDENCIES.get(1);
        Dependency profile = AccountDeletionClient.DEPENDENCIES.get(2);
        when(deletion.delete(gameLogic, userId)).thenReturn(true);
        when(deletion.delete(tutor, userId)).thenReturn(false);

        mvc.perform(delete("/internal/auth/account").header("X-User-Id", userId))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error.code").value("SERVICES_UNAVAILABLE"));

        verify(deletion, never()).delete(profile, userId);
        assertThat(users.existsById(userId)).isTrue();

        // Reintento cuando Tutor vuelve: se repiten las tres llamadas y ahora sí se borra.
        when(deletion.delete(any(Dependency.class), eq(userId))).thenReturn(true);
        mvc.perform(delete("/internal/auth/account").header("X-User-Id", userId))
                .andExpect(status().isNoContent());
        assertThat(users.existsById(userId)).isFalse();
    }

    @Test
    void deletingAnAlreadyDeletedAccountIsA204() throws Exception {
        mvc.perform(delete("/internal/auth/account").header("X-User-Id", "11111111-1111-4111-8111-111111111111"))
                .andExpect(status().isNoContent());
        verifyNoInteractions(deletion);
    }

    @Test
    void deleteWithoutUserHeaderIsAValidationError() throws Exception {
        mvc.perform(delete("/internal/auth/account"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
    }
}
