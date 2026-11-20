package com.chess.gameservice.client;

import com.chess.gameservice.error.ApiException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import java.io.IOException;
import java.io.InputStream;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Map;
import java.util.function.Supplier;

/** Utilidades compartidas por los clientes REST (Game Logic y Botcito, ambos por el gateway interno). */
final class RestClients {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    /** Errores 5xx del catálogo que pasan con su código y estado reales (contrato, 4.5). */
    private static final Map<String, HttpStatus> CATALOG_5XX = Map.of(
            "SERVICES_UNAVAILABLE", HttpStatus.SERVICE_UNAVAILABLE,
            "ENGINE_BUSY", HttpStatus.SERVICE_UNAVAILABLE,
            "ENGINE_TIMEOUT", HttpStatus.GATEWAY_TIMEOUT);

    private RestClients() {
    }

    static RestClient create(String baseUrl, Duration readTimeout) {
        // JdkClientHttpRequestFactory: SimpleClientHttpRequestFactory no soporta PATCH.
        // HTTP/1.1 para evitar problemas con servidores simples (Python http.server, etc.).
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(client);
        factory.setReadTimeout(readTimeout);
        return RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
    }

    /**
     * Convierte una respuesta de error del servicio remoto en ApiException.
     * Los 4xx conservan estado y código (ya vienen con la forma del contrato). Los 5xx conservan
     * ENGINE_BUSY (503), ENGINE_TIMEOUT (504) y SERVICES_UNAVAILABLE (503); cualquier otro 5xx
     * pasa a 503 SERVICES_UNAVAILABLE.
     */
    static ApiException toApiException(String service, int status, InputStream body) {
        String code = null;
        String message = null;
        try {
            JsonNode error = MAPPER.readTree(body).path("error");
            code = error.path("code").asText(null);
            message = error.path("message").asText(null);
        } catch (IOException | RuntimeException ignored) {
            // cuerpo vacío o que no es JSON
        }

        HttpStatus resolved = HttpStatus.resolve(status);
        if (resolved == null || resolved.is5xxServerError()) {
            HttpStatus catalog = code == null ? null : CATALOG_5XX.get(code);
            if (catalog != null) {
                return new ApiException(catalog, code, message != null ? message : service + " no está disponible");
            }
            return ApiException.unavailable(service + " respondió con error " + status);
        }
        return new ApiException(resolved,
                code != null ? code : "UPSTREAM_ERROR",
                message != null ? message : service + " respondió " + status);
    }

    /** Ejecuta la llamada y convierte los fallos de red en 503 SERVICES_UNAVAILABLE. */
    static <T> T call(String service, Supplier<T> action) {
        try {
            return action.get();
        } catch (ResourceAccessException e) {
            throw ApiException.unavailable("No se pudo conectar con " + service);
        }
    }

    /** Ejecuta la petición, traduce los errores remotos y exige un cuerpo. */
    static <T> T exchange(String service, RestClient.RequestHeadersSpec<?> request, Class<T> type) {
        T result = call(service, () -> request
                .retrieve()
                .onStatus(s -> s.isError(), (req, res) -> {
                    throw toApiException(service, res.getStatusCode().value(), res.getBody());
                })
                .body(type));
        if (result == null) {
            throw ApiException.unavailable(service + " devolvió una respuesta vacía");
        }
        return result;
    }
}
