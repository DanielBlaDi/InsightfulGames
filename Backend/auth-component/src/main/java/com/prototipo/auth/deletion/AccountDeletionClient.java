package com.prototipo.auth.deletion;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * Pide a los servicios dependientes que borren los datos de un usuario, llamándolos directamente
 * (contrato v9, sección 7). El orden es fijo: Game Logic, Tutor y Profile/Stats.
 */
@Component
public class AccountDeletionClient {

    /** Servicio dependiente y su ruta interna de borrado. */
    public record Dependency(String name, String pathTemplate) {
    }

    public static final List<Dependency> DEPENDENCIES = List.of(
            new Dependency("Game Logic", "/internal/logic/users/{userId}"),
            new Dependency("Tutor", "/internal/tutor/users/{userId}"),
            new Dependency("Profile/Stats", "/internal/profile/users/{userId}"));

    private static final Logger log = LoggerFactory.getLogger(AccountDeletionClient.class);

    /** Un cliente por servicio, indexado por {@link Dependency#name()}. */
    private final Map<String, RestClient> clients;

    @Autowired
    public AccountDeletionClient(@Value("${services.game-logic-url}") String gameLogicUrl,
                                 @Value("${services.tutor-url}") String tutorUrl,
                                 @Value("${services.profile-url}") String profileUrl,
                                 @Value("${services.timeout-seconds}") long timeoutSeconds) {
        this.clients = Map.of(
                DEPENDENCIES.get(0).name(), client(gameLogicUrl, timeoutSeconds),
                DEPENDENCIES.get(1).name(), client(tutorUrl, timeoutSeconds),
                DEPENDENCIES.get(2).name(), client(profileUrl, timeoutSeconds));
    }

    /** Para pruebas: un solo builder (con servidor simulado) atiende a los tres servicios. */
    public AccountDeletionClient(RestClient.Builder builder) {
        RestClient shared = builder.build();
        this.clients = Map.of(
                DEPENDENCIES.get(0).name(), shared,
                DEPENDENCIES.get(1).name(), shared,
                DEPENDENCIES.get(2).name(), shared);
    }

    private static RestClient client(String baseUrl, long timeoutSeconds) {
        return RestClient.builder().baseUrl(baseUrl)
                .requestFactory(requestFactory(timeoutSeconds)).build();
    }

    /**
     * true solo si el servicio respondió 204, que es lo que promete el contrato aunque no haya
     * datos que borrar. Cualquier otra respuesta o un fallo de red cuentan como no disponible.
     */
    public boolean delete(Dependency dependency, String userId) {
        try {
            HttpStatus status = HttpStatus.valueOf(clients.get(dependency.name()).delete()
                    .uri(dependency.pathTemplate(), userId)
                    .retrieve()
                    .onStatus(s -> true, (request, response) -> { })
                    .toBodilessEntity()
                    .getStatusCode()
                    .value());
            if (status != HttpStatus.NO_CONTENT) {
                log.warn("{} respondió {} al borrar el usuario {}", dependency.name(), status.value(), userId);
            }
            return status == HttpStatus.NO_CONTENT;
        } catch (RestClientException | IllegalArgumentException e) {
            log.warn("{} no respondió al borrar el usuario {}: {}", dependency.name(), userId, e.toString());
            return false;
        }
    }

    private static JdkClientHttpRequestFactory requestFactory(long timeoutSeconds) {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(timeoutSeconds))
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(client);
        factory.setReadTimeout(Duration.ofSeconds(timeoutSeconds));
        return factory;
    }
}
