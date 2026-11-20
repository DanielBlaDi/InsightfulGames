package worker;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import worker.TimeoutService.Outcome;

/** Ciclo de cierre contra un gateway interno falso, con un RestClient real. */
class TimeoutServiceTest{

    static final String A = "aaaaaaaa-0000-4000-8000-000000000001";
    static final String B = "bbbbbbbb-0000-4000-8000-000000000002";
    static final String C = "cccccccc-0000-4000-8000-000000000003";

    private FakeGateway gateway;
    private TimeoutService service;

    @BeforeEach
    void setUp() throws Exception{
        gateway = new FakeGateway();
        WorkerProperties properties = new WorkerProperties(gateway.url() + "/", 1, 25);
        service = new TimeoutService(RestClientConfig.create(properties.gatewayInternalUrl()), properties,
            new WorkerHealth(properties));
    }

    @AfterEach
    void tearDown(){
        gateway.close();
    }

    private static String item(String id, int version, String reason){
        return "{\"gameId\":\"" + id + "\",\"version\":" + version + ",\"reason\":\"" + reason + "\"}";
    }

    @Test
    void queriesExpiredGamesWithTheConfiguredLimitThroughTheGateway(){
        service.runCycle();

        FakeGateway.Request get = gateway.requests.get(0);
        assertEquals("GET", get.method());
        assertEquals("/internal/logic/games/expired", get.path());
        assertEquals("limit=25", get.query());
        assertTrue(gateway.posts().isEmpty());
    }

    @Test
    void clockGamesAreTimedOutAndWaitingGamesExpiredWithExpectedVersion(){
        // Vocabulario del contrato (clock, waiting) y el que hoy devuelve Game Logic (timeout, expired)
        gateway.expired = new FakeGateway.Reply(200, "[" + item(A, 7, "clock") + "," + item(B, 3, "waiting") + ","
            + item(C, 9, "timeout") + "," + item("dddddddd-0000-4000-8000-000000000004", 1, "expired") + "]");

        Map<Outcome, Integer> result = service.runCycle();

        assertEquals(Map.of(Outcome.CLOSED, 4), result);
        List<FakeGateway.Request> posts = gateway.posts();
        assertEquals("/internal/logic/games/" + A + "/timeout", posts.get(0).path());
        assertEquals("{\"expectedVersion\":7}", posts.get(0).body().replace(" ", ""));
        assertTrue(posts.get(0).contentType().startsWith("application/json"));
        assertEquals("/internal/logic/games/" + B + "/expire", posts.get(1).path());
        assertEquals("{\"expectedVersion\":3}", posts.get(1).body().replace(" ", ""));
        assertEquals("/internal/logic/games/" + C + "/timeout", posts.get(2).path());
        assertEquals("/internal/logic/games/dddddddd-0000-4000-8000-000000000004/expire", posts.get(3).path());
    }

    @Test
    void expectedErrorsAreIgnoredAndOthersDoNotStopTheBatch(){
        gateway.expired = new FakeGateway.Reply(200, "[" + item(A, 1, "clock") + "," + item(B, 2, "waiting") + ","
            + item(C, 3, "clock") + "," + item("dddddddd-0000-4000-8000-000000000004", 4, "clock") + ","
            + item("eeeeeeee-0000-4000-8000-000000000005", 5, "waiting") + "]");
        gateway.replyTo("/internal/logic/games/" + A + "/timeout", 409, "VERSION_CONFLICT");
        gateway.replyTo("/internal/logic/games/" + B + "/expire", 422, "WAITING_NOT_EXPIRED");
        gateway.replyTo("/internal/logic/games/" + C + "/timeout", 503, "SERVICES_UNAVAILABLE");
        gateway.replyTo("/internal/logic/games/dddddddd-0000-4000-8000-000000000004/timeout", 404, "GAME_NOT_FOUND");

        Map<Outcome, Integer> result = service.runCycle();

        assertEquals(Map.of(Outcome.IGNORED, 2, Outcome.FAILED, 1, Outcome.REJECTED, 1, Outcome.CLOSED, 1), result);
        assertEquals(5, gateway.posts().size());
    }

    @Test
    void allContractIgnoredCodesAreIgnored(){
        for(String code : TimeoutService.IGNORED_CODES){
            gateway.replyTo("/internal/logic/games/" + A + "/timeout", code.equals("VERSION_CONFLICT") ? 409 : 422, code);
            assertEquals(Outcome.IGNORED, service.process(new ExpiredQueryResponse(A, 1, "clock")), code);
        }
    }

    @Test
    void invalidItemsAndUnknownReasonsAreSkipped(){
        gateway.expired = new FakeGateway.Reply(200, "[{\"gameId\":null,\"version\":1,\"reason\":\"clock\"},"
            + "{\"gameId\":\"" + A + "\",\"version\":null,\"reason\":\"clock\"}," + item(B, 1, "draw") + ","
            + item(C, 2, "clock") + "]");

        Map<Outcome, Integer> result = service.runCycle();

        assertEquals(Map.of(Outcome.SKIPPED, 3, Outcome.CLOSED, 1), result);
        assertEquals(1, gateway.posts().size());
    }

    @Test
    void failingQueryEndsTheCycleWithoutPosts(){
        gateway.expired = new FakeGateway.Reply(503, "{\"error\":{\"code\":\"SERVICES_UNAVAILABLE\",\"message\":\"m\"}}");
        assertEquals(Map.of(), service.runCycle());

        gateway.expired = new FakeGateway.Reply(400, "{\"error\":{\"code\":\"VALIDATION_ERROR\",\"message\":\"m\"}}");
        assertEquals(Map.of(), service.runCycle());
        assertTrue(gateway.posts().isEmpty());
    }

    @Test
    void unreachableGatewayDoesNotThrow(){
        gateway.close();
        assertEquals(Map.of(), service.runCycle());
        service.periodicallyTimeoutAndExpireMatches(); // el método programado tampoco lanza
    }

    @Test
    void healthGoesStaleWhenTheCycleStopsBeatingAndRecoversOnTheNextBeat(){
        Instant start = Instant.parse("2026-11-03T10:00:00Z");
        MutableClock clock = new MutableClock(start);
        WorkerHealth health = new WorkerHealth(clock, Duration.ofSeconds(60));

        assertTrue(health.isHealthy());
        clock.now = start.plusSeconds(60);
        assertTrue(health.isHealthy());
        clock.now = start.plusSeconds(61);
        assertEquals(false, health.isHealthy());
        health.beat();
        assertTrue(health.isHealthy());
    }

    static final class MutableClock extends Clock{
        Instant now;

        MutableClock(Instant now){
            this.now = now;
        }

        @Override
        public ZoneOffset getZone(){
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(java.time.ZoneId zone){
            return this;
        }

        @Override
        public Instant instant(){
            return now;
        }
    }
}
