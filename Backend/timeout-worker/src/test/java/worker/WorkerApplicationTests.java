package worker;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * Arranque completo con las mismas variables que da Compose: el planificador consulta al gateway
 * con el límite configurado, cierra lo vencido y /health y la opción -health responden.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WorkerApplicationTests{

    static final String GAME = "aaaaaaaa-0000-4000-8000-000000000001";
    static final FakeGateway gateway;

    static{
        try{
            gateway = new FakeGateway();
        }catch(IOException e){
            throw new IllegalStateException(e);
        }
        gateway.expired = new FakeGateway.Reply(200,
            "[{\"gameId\":\"" + GAME + "\",\"version\":4,\"reason\":\"timeout\"}]");
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry){
        registry.add("PORT", () -> "0");
        registry.add("GATEWAY_INTERNAL_URL", gateway::url);
        registry.add("TIMEOUT_POLL_INTERVAL_SECONDS", () -> "1");
        registry.add("TIMEOUT_BATCH_LIMIT", () -> "100");
    }

    @AfterAll
    static void stop(){
        gateway.close();
    }

    @Value("${local.server.port}")
    int port;

    @Test
    void schedulerPollsTheGatewayAndClosesExpiredGames() throws Exception{
        long deadline = System.currentTimeMillis() + 10_000;
        while(gateway.posts().isEmpty() && System.currentTimeMillis() < deadline){
            Thread.sleep(100);
        }
        FakeGateway.Request get = gateway.requests.stream().filter(r -> r.method().equals("GET")).findFirst().orElseThrow();
        assertEquals("/internal/logic/games/expired", get.path());
        assertEquals("limit=100", get.query());
        FakeGateway.Request post = gateway.posts().get(0);
        assertEquals("/internal/logic/games/" + GAME + "/timeout", post.path());
        assertEquals("{\"expectedVersion\":4}", post.body().replace(" ", ""));
    }

    @Test
    void healthEndpointAndProbeReportOk() throws Exception{
        HttpResponse<String> response = HttpClient.newHttpClient().send(
            HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/health")).build(),
            HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"status\":\"ok\""));

        assertEquals(0, HealthProbe.run(String.valueOf(port)));
        assertEquals(1, HealthProbe.run(null));
        assertEquals(1, HealthProbe.run("1")); // nada escucha en el puerto 1
        assertTrue(HealthProbe.requested(new String[]{"-health"}));
    }
}
