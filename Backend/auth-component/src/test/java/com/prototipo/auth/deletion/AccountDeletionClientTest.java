package com.prototipo.auth.deletion;

import com.prototipo.auth.deletion.AccountDeletionClient.Dependency;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.io.IOException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withNoContent;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;

/** Llamadas reales de RestClient contra un gateway simulado. */
class AccountDeletionClientTest {

    private static final String USER = "11111111-1111-4111-8111-111111111111";

    private final RestClient.Builder builder = RestClient.builder().baseUrl("http://gateway:8080");
    private final MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
    private final AccountDeletionClient client = new AccountDeletionClient(builder);

    @Test
    void usesTheInternalRoutesOfTheContract() {
        server.expect(requestTo("http://gateway:8080/internal/logic/users/" + USER))
                .andExpect(method(HttpMethod.DELETE)).andRespond(withNoContent());
        server.expect(requestTo("http://gateway:8080/internal/tutor/users/" + USER))
                .andExpect(method(HttpMethod.DELETE)).andRespond(withNoContent());
        server.expect(requestTo("http://gateway:8080/internal/profile/users/" + USER))
                .andExpect(method(HttpMethod.DELETE)).andRespond(withNoContent());

        for (Dependency dependency : AccountDeletionClient.DEPENDENCIES) {
            assertThat(client.delete(dependency, USER)).isTrue();
        }
        server.verify();
    }

    @Test
    void anythingOtherThan204CountsAsUnavailable() {
        Dependency profile = AccountDeletionClient.DEPENDENCIES.get(2);
        server.expect(requestTo("http://gateway:8080/internal/profile/users/" + USER))
                .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));
        server.expect(requestTo("http://gateway:8080/internal/profile/users/" + USER))
                .andRespond(withStatus(HttpStatus.OK));
        server.expect(requestTo("http://gateway:8080/internal/profile/users/" + USER))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        assertThat(client.delete(profile, USER)).isFalse();
        assertThat(client.delete(profile, USER)).isFalse();
        assertThat(client.delete(profile, USER)).isFalse();
    }

    @Test
    void networkFailuresCountAsUnavailable() {
        server.expect(requestTo("http://gateway:8080/internal/logic/users/" + USER))
                .andRespond(withException(new IOException("conexión rechazada")));

        assertThat(client.delete(AccountDeletionClient.DEPENDENCIES.get(0), USER)).isFalse();
    }
}
