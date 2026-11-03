package com.chess.gameservice.rest;

import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.CreateGameRequest;
import com.chess.gameservice.model.GameState;
import com.chess.gameservice.model.ResignRequest;
import com.chess.gameservice.model.VisibilityRequest;
import com.chess.gameservice.service.SinglePlayerService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/** Rutas REST internas de Single Player (contrato, 12.4). Los gateways envían siempre X-User-Id. */
@RestController
public class GameController {

    private static final String USER_HEADER = "X-User-Id";
    private static final String GAMES = "/internal/single-player/games";

    private final SinglePlayerService service;

    public GameController(SinglePlayerService service) {
        this.service = service;
    }

    @PostMapping(GAMES)
    public ResponseEntity<GameState> create(@RequestHeader(name = USER_HEADER, required = false) String userId,
                                            @RequestBody(required = false) CreateGameRequest request) {
        GameState state = service.createGame(requireUser(userId), request);
        return ResponseEntity.status(HttpStatus.CREATED).body(state);
    }

    @GetMapping(GAMES + "/{id}")
    public GameState get(@RequestHeader(name = USER_HEADER, required = false) String userId,
                         @PathVariable("id") String id) {
        return service.getGame(requireUser(userId), id);
    }

    @PostMapping(GAMES + "/{id}/resign")
    public GameState resign(@RequestHeader(name = USER_HEADER, required = false) String userId,
                            @PathVariable("id") String id,
                            @RequestBody(required = false) ResignRequest request) {
        return service.resign(requireUser(userId), id, request == null ? null : request.side());
    }

    @PatchMapping(GAMES + "/{id}/visibility")
    public GameState visibility(@RequestHeader(name = USER_HEADER, required = false) String userId,
                                @PathVariable("id") String id,
                                @RequestBody(required = false) VisibilityRequest request) {
        String user = requireUser(userId);
        if (request == null) {
            throw ApiException.validation("Falta el cuerpo de la petición");
        }
        return service.changeVisibility(user, id, request.visibility(), request.expectedVersion());
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    private static String requireUser(String userId) {
        if (userId == null || userId.isBlank()) {
            throw ApiException.unauthorized();
        }
        return userId;
    }
}
