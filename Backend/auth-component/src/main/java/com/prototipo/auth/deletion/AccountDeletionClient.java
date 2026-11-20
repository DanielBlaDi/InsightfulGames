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

/**
 * Pide a los servicios dependientes que borren los datos de un usuario, por el gateway interno
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

    private final RestClient http;

    @Autowired
    public AccountDeletionClient(@Value("${gateway.internal-url}") String gatewayUrl,
                                 @Value("${gateway.timeout-seconds}") long timeoutSeconds) {
        this(RestClient.builder().baseUrl(gatewayUrl).requestFactory(requestFactory(timeoutSeconds)));
    }

    /** Para pruebas: permite enlazar un servidor simulado al builder. */
    public AccountDeletionClient(RestClient.Builder builder) {
        this.http = builder.build();
    }

    /**
     * true solo si el servicio respondió 204, que es lo que promete el contrato aunque no haya
     * datos que borrar. Cualquier otra respuesta o un fallo de red cuentan como no disponible.
     */
    public boolean delete(Dependency dependency, String userId) {
        try {
            HttpStatus status = HttpStatus.valueOf(http.delete()
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
