package com.chess.gameservice.rest;

import com.chess.gameservice.error.ApiException;
import com.chess.gameservice.model.CreateGameRequest;
import com.chess.gameservice.model.GameState;
import com.chess.gameservice.model.GameSummary;
import com.chess.gameservice.model.ResignRequest;
import com.chess.gameservice.service.SinglePlayerService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/** Rutas REST de la sección 3.4. El Gateway envía siempre X-User-Id. */
@RestController
public class GameController {

    private static final String USER_HEADER = "X-User-Id";

    private final SinglePlayerService service;

    public GameController(SinglePlayerService service) {
        this.service = service;
    }

    @PostMapping("/games")
    public ResponseEntity<GameState> create(@RequestHeader(name = USER_HEADER, required = false) String userId,
                                            @RequestBody CreateGameRequest request) {
        GameState state = service.createGame(requireUser(userId), request);
        return ResponseEntity.status(HttpStatus.CREATED).body(state);
    }

    @GetMapping("/games/{id}")
    public GameState get(@RequestHeader(name = USER_HEADER, required = false) String userId,
                         @PathVariable("id") String id) {
        return service.getGame(requireUser(userId), id);
    }

    @GetMapping("/games")
    public List<GameSummary> list(@RequestHeader(name = USER_HEADER, required = false) String userId) {
        return service.listGames(requireUser(userId));
    }

    @PostMapping("/games/{id}/resign")
    public GameState resign(@RequestHeader(name = USER_HEADER, required = false) String userId,
                            @PathVariable("id") String id,
                            @RequestBody(required = false) ResignRequest request) {
        return service.resign(requireUser(userId), id, request == null ? null : request.side());
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
