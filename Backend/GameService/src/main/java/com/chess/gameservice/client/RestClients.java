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
import java.util.function.Supplier;

/** Utilidades compartidas por los clientes REST (Game Logic y Botcito). */
final class RestClients {

    private static final ObjectMapper MAPPER = new ObjectMapper();

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
     * Los 4xx conservan estado y código (ya vienen con la forma del contrato); los 5xx pasan a 502.
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
            return ApiException.unavailable(service + " respondió con error " + status);
        }
        return new ApiException(resolved,
                code != null ? code : "UPSTREAM_ERROR",
                message != null ? message : service + " respondió " + status);
    }

    /** Ejecuta la llamada y convierte los fallos de red en un 502 con código SERVICE_UNAVAILABLE. */
    static <T> T call(String service, Supplier<T> action) {
        try {
            return action.get();
        } catch (ResourceAccessException e) {
            throw ApiException.unavailable("No se pudo conectar con " + service);
        }
    }
}
