package com.prototipo.auth;

import com.prototipo.auth.outbox.EventSender;
import com.prototipo.auth.outbox.OutboxEvent;
import com.prototipo.auth.outbox.OutboxRelay;
import com.prototipo.auth.outbox.OutboxRepository;
import com.prototipo.auth.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.amqp.AmqpConnectException;
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

import java.net.ConnectException;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Registro, login y outbox de user.registered sobre H2 (modo MySQL). El broker se simula. */
@SpringBootTest
@ActiveProfiles("test")
class AuthIntegrationTest {

    @Autowired private WebApplicationContext context;
    @Autowired private UserRepository users;
    @Autowired private OutboxRepository outbox;
    @Autowired private OutboxRelay relay;
    @Autowired private JsonMapper mapper;

    @MockitoBean private EventSender sender;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        users.deleteAllInBatch();
        outbox.deleteAllInBatch();
        reset(sender);
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
    void registrationStoresUserRegisteredInTheOutbox() throws Exception {
        String userId = register("/internal/auth/register", "ana");

        List<OutboxEvent> pending = outbox.findAll();
        assertThat(pending).hasSize(1);
        OutboxEvent row = pending.get(0);
        assertThat(row.getExchange()).isEqualTo("user.events");
        assertThat(row.getRoutingKey()).isEqualTo("user.registered");
        assertThat(row.getPublishedAt()).isNull();
        JsonNode event = mapper.readTree(row.getPayload());
        assertThat(event.get("eventId").asString()).isEqualTo(row.getEventId()).matches("[0-9a-f-]{36}");
        assertThat(event.get("eventType").asString()).isEqualTo("user.registered");
        assertThat(event.get("userId").asString()).isEqualTo(userId);
        assertThat(event.get("username").asString()).isEqualTo("ana");
        assertThat(event.get("occurredAt").asString()).endsWith("Z");
    }

    @Test
    void relayPublishesAndMarksTheEvent() throws Exception {
        register("/internal/auth/register", "ana");

        assertThat(relay.publishPending()).isEqualTo(1);

        ArgumentCaptor<OutboxEvent> sent = ArgumentCaptor.forClass(OutboxEvent.class);
        verify(sender).send(sent.capture());
        assertThat(sent.getValue().getRoutingKey()).isEqualTo("user.registered");
        assertThat(outbox.countByPublishedAtIsNull()).isZero();
        assertThat(relay.publishPending()).isZero();
        verify(sender, times(1)).send(any());
    }

    @Test
    void eventSurvivesARabbitOutageAndIsPublishedLater() throws Exception {
        doThrow(new AmqpConnectException(new ConnectException("broker caído"))).when(sender).send(any());

        String userId = register("/internal/auth/register", "bea");
        assertThat(relay.publishPending()).isZero();
        assertThat(relay.publishPending()).isZero();

        assertThat(users.existsById(userId)).isTrue();
        OutboxEvent row = outbox.findAll().get(0);
        assertThat(row.getPublishedAt()).isNull();
        assertThat(row.getAttempts()).isEqualTo(2);
        assertThat(row.getLastError()).contains("broker caído");

        doNothing().when(sender).send(any());
        assertThat(relay.publishPending()).isEqualTo(1);
        assertThat(outbox.countByPublishedAtIsNull()).isZero();
    }

    @Test
    void relayKeepsOrderAndStopsAtTheFirstFailure() throws Exception {
        register("/internal/auth/register", "ana");
        register("/internal/auth/register", "bea");
        register("/internal/auth/register", "cris");
        List<OutboxEvent> rows = outbox.findTop50ByPublishedAtIsNullOrderByCreatedAtAsc();
        String second = rows.get(1).getEventId();
        doThrow(new AmqpConnectException(new ConnectException("x")))
                .when(sender).send(org.mockito.ArgumentMatchers.argThat(e -> e != null && e.getEventId().equals(second)));

        assertThat(relay.publishPending()).isEqualTo(1);

        assertThat(outbox.countByPublishedAtIsNull()).isEqualTo(2);
        assertThat(outbox.findTop50ByPublishedAtIsNullOrderByCreatedAtAsc().get(0).getEventId()).isEqualTo(second);
    }

    @Test
    void failedRegistrationLeavesNoEvent() throws Exception {
        register("/internal/auth/register", "ana");
        outbox.deleteAllInBatch();

        mvc.perform(post("/internal/auth/register").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"ana\",\"password\":\"otraClave123\"}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("USERNAME_TAKEN"))
                .andExpect(jsonPath("$.error.message").isString());

        assertThat(outbox.count()).isZero();
        verifyNoInteractions(sender);
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
}
