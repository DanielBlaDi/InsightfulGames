package worker;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;

import org.junit.jupiter.api.Test;

class WorkerPropertiesTest{

    @Test
    void rejectsMissingOrInvalidValues(){
        assertThrows(IllegalArgumentException.class, () -> new WorkerProperties(null, 1, 100));
        assertThrows(IllegalArgumentException.class, () -> new WorkerProperties("/internal/logic/games/", 1, 100));
        assertThrows(IllegalArgumentException.class, () -> new WorkerProperties("http://gw:8080", 0, 100));
        assertThrows(IllegalArgumentException.class, () -> new WorkerProperties("http://gw:8080", null, 100));
        assertThrows(IllegalArgumentException.class, () -> new WorkerProperties("http://gw:8080", 1, 0));
    }

    @Test
    void normalizesTheBaseUrlAndDerivesTheStaleThreshold(){
        WorkerProperties properties = new WorkerProperties("http://api-gateway-component:8080/", 1, 100);
        assertEquals("http://api-gateway-component:8080", properties.gatewayInternalUrl());
        assertEquals(Duration.ofSeconds(60), properties.staleAfter());
        assertEquals(Duration.ofSeconds(300), new WorkerProperties("http://gw", 30, 1).staleAfter());
    }
}
