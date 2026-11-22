package com.chess.gameservice.rest;

import com.chess.gameservice.model.PublishRequest;
import com.chess.gameservice.service.SinglePlayerService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Ruta interna de Single Player como hub de sesiones. Las operaciones REST (crear, leer, rendirse, cambiar
 * la visibilidad) las orquesta el gateway contra Game Logic; aquí solo llega el aviso para los clientes.
 */
@RestController
public class GameController {

    private static final String GAMES = "/internal/single-player/games";

    private final SinglePlayerService service;

    public GameController(SinglePlayerService service) {
        this.service = service;
    }

    /** El gateway ya operó en Game Logic: este hub avisa por WebSocket y no consulta a nadie. */
    @PostMapping(GAMES + "/{id}/publish")
    public ResponseEntity<Void> publish(@PathVariable("id") String id,
                                        @RequestBody(required = false) PublishRequest request) {
        service.applyPublish(id, request);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
