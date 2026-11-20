package worker;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkerController{

    private final WorkerHealth health;

    WorkerController(WorkerHealth health){
        this.health = health;
    }

    /** 200 { status: ok } si el ciclo sigue activo; 503 si se detuvo. No consulta a Game Logic. */
    @GetMapping({"/health", "/health/"})
    ResponseEntity<Map<String, String>> health(){
        if(health.isHealthy()){
            return ResponseEntity.ok(Map.of("status", "ok"));
        }
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of("status", "stalled", "lastActivity", health.lastActivity().toString()));
    }
}
