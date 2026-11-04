package chess.matches;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import chess.constants.Color;
import chess.constants.EndReason;
import chess.constants.Mode;
import chess.constants.Result;
import chess.constants.Status;
import chess.constants.Visibility;
import chess.exceptions.*;
import chess.matches.ChessRules.Applied;
import chess.movements.Movement;
import chess.movements.MovementCreationEssentials;

/**
 * Rutas internas de Game Logic (contrato, 11.4). Game Logic no decide permisos: valida reglas,
 * reloj, versión y fin de partida.
 *
 * <p>Toda escritura de una partida existente es atómica y condicionada por la versión leída
 * (11.4.7). Las operaciones con expectedVersion (moves, visibility, timeout, expire) responden
 * VERSION_CONFLICT si pierden la condición. Las demás (join, resign, abandon, draw/* y borrado)
 * releen y reintentan hasta 3 veces antes de responder VERSION_CONFLICT. game.finished se publica
 * siempre después de guardar (11.4.10).
 */
@RestController
public class MatchController{
    private static final Pattern UUID_FORMAT = Pattern.compile("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");

    /** Reintentos de las escrituras sin expectedVersion (contrato, 11.4.7). */
    static final int MAX_WRITE_RETRIES = 3;

    /** Valor de reason en GET .../expired (contrato, 11.4). */
    static final String REASON_CLOCK = "clock";
    static final String REASON_WAITING = "waiting";

    private final MatchRepository repository;
    private final MatchStore store;
    private final MatchAssembler assembler;
    private final RabbitPublisher publisher;
    private final GameLogicProperties properties;

    MatchController(MatchRepository repository, MatchStore store, MatchAssembler assembler, RabbitPublisher publisher, GameLogicProperties properties){
        this.repository = repository;
        this.store = store;
        this.assembler = assembler;
        this.publisher = publisher;
        this.properties = properties;
    }

    /** Valida, cambia y marca la versión nueva sobre la partida recién leída. */
    @FunctionalInterface
    private interface Change{
        void apply(Match match);
    }

    /** Crea la partida en la posición inicial, o devuelve la existente si la creación es repetida. */
    @PostMapping({"/internal/logic/games", "/internal/logic/games/"})
    ResponseEntity<GameState> newMatch(@RequestBody(required = false) CreateMatchRequest request){
        Match newMatch = buildNewMatch(request);

        if(newMatch.getCreationKey() != null){
            Optional<Match> existing = repository.findByCreationKey(newMatch.getCreationKey());
            if(existing.isPresent()){
                return repeatedCreation(existing.get(), newMatch);
            }
        }

        // local y vs_bot empiezan su reloj al crearse; multijugador, en join (11.4.9)
        if(!Mode.MULTIPLAYER.toString().equals(newMatch.getMode())){
            newMatch.startClock();
        }

        Match saved;
        try{
            saved = store.insert(newMatch);
        }catch(DuplicateKeyException exception){
            // Carrera resuelta por el índice único: quien pierde relee y aplica las reglas (11.4.5)
            Optional<Match> winner = newMatch.getCreationKey() == null ? Optional.empty() : repository.findByCreationKey(newMatch.getCreationKey());
            if(winner.isPresent()){
                return repeatedCreation(winner.get(), newMatch);
            }
            throw exception;
        }

        return ResponseEntity.created(URI.create("/internal/logic/games/" + saved.getGameId())).body(assembler.toState(saved));
    }

    private ResponseEntity<GameState> repeatedCreation(Match existing, Match requested){
        if(!existing.getRequestFingerPrint().equals(requested.getRequestFingerPrint())){
            throw CreationKeyException.keyReused();
        }
        return ResponseEntity.ok(assembler.toState(existing));
    }

    @GetMapping({"/internal/logic/games/{id}", "/internal/logic/games/{id}/"})
    GameState getMatchByGameId(@PathVariable("id") String id){
        return assembler.toState(findMatch(id));
    }

    @GetMapping({"/internal/logic/games/by-match/{matchId}", "/internal/logic/games/by-match/{matchId}/"})
    ResponseEntity<GameState> getGameIdByMatchId(@PathVariable("matchId") String matchId){
        Optional<Match> foundMatch = repository.findByMatchId(matchId);

        if(foundMatch.isPresent()){
            return ResponseEntity.ok(assembler.toState(foundMatch.get()));
        }else{
            throw MatchNotFoundException.notFound(matchId);
        }
    }

    /** Las partidas de un usuario, la más reciente primero. */
    @GetMapping({"/internal/logic/games", "/internal/logic/games/"})
    ResponseEntity<GamesPage> getMatchesByUserIdPaged(@RequestParam(name = "userId", required = false) String userId, @RequestParam(name = "limit", required = false) Integer limit, @RequestParam(name = "cursor", required = false) String cursor){
        if(userId == null || userId.isBlank()){
            throw RequestNotValidException.notValid("Falta el parámetro userId");
        }

        if(limit == null){
            limit = 20;
        }else if(limit > 20 || limit < 1){
            throw RequestNotValidException.notValid("El parámetro limit debe ser un valor entre 1 y 20 inclusivos");
        }

        List<GameSummary> matchList = repository.findByParticipantsUserIdOrderByCreatedAtDesc(userId).stream()
            .map(match -> assembler.toSummary(match, userId))
            .toList();

        GamesPage result;
        int decodedCursor;

        if(cursor == null){
            decodedCursor = 1;
        }else{
            try{
                decodedCursor = Integer.parseInt(new String(Base64.getUrlDecoder().decode(cursor), StandardCharsets.UTF_8));
                if(decodedCursor <= 0){
                    throw new IllegalArgumentException();
                }
            }catch(IllegalArgumentException exception){
                throw RequestNotValidException.notValid("El parámetro cursor no representa un valor válido de cursor en base64url");
            }
        }

        // long: evita desbordar int con cursores grandes. Una página más allá del final es una página vacía, no un error.
        long fromLong = (long) limit * (decodedCursor - 1);
        int total = matchList.size();
        int from = (int) Math.min(fromLong, total);
        int to = (int) Math.min(fromLong + limit, total);
        String nextCursor = (fromLong + limit < total)
            ? Base64.getUrlEncoder().withoutPadding().encodeToString(String.valueOf(decodedCursor + 1).getBytes(StandardCharsets.UTF_8))
            : null;
        result = new GamesPage(matchList.subList(from, to), nextCursor);

        return ResponseEntity.ok(result);
    }

    @PostMapping({"/internal/logic/games/{id}/join", "/internal/logic/games/{id}/join/"})
    ResponseEntity<GameState> joinMatch(@PathVariable("id") String id, @RequestBody(required = false) JoinMatchRequestBody requestBody){
        if(requestBody == null || !isUuid(requestBody.userId())){
            throw RequestNotValidException.notValid("userId debe ser un UUID");
        }
        String userId = requestBody.userId();

        Match joined = updateWithRetry(id, match -> {
            if(!match.isWaiting()){
                throw CannotJoinMatchException.notWaiting();
            }
            if(match.participantWithUserId(userId) != null){
                throw CannotJoinMatchException.alreadyParticipant();
            }
            String creatorColor = match.getParticipants().get(0).color();
            match.addParticipant(new Participant(userId, opposite(creatorColor)));
            match.setStatus(Status.IN_PROGRESS.toString());
            match.startClock();
            match.updateVersion();
        });

        return ResponseEntity.ok(assembler.toState(joined));
    }

    /**
     * Aplica una jugada UCI sobre la posición guardada (contrato, 11.4.8). Compara versión y reloj
     * antes de aplicar. Una partida sin reloj (timeControl null) nunca vence.
     */
    @PostMapping({"/internal/logic/games/{id}/moves", "/internal/logic/games/{id}/moves/"})
    GameState addMovement(@PathVariable("id") String id, @RequestBody(required = false) MovementCreationEssentials movement){
        Match match = findMatch(id);
        Instant turnEndInstant = Instant.now();

        if(movement == null || movement.uci() == null || movement.uci().isBlank()){
            throw RequestNotValidException.notValid("Falta el campo uci");
        }
        if(movement.expectedVersion() == null){
            throw RequestNotValidException.notValid("Falta el campo expectedVersion");
        }
        requireInProgress(match);
        int readVersion = match.getVersion();
        if(readVersion != movement.expectedVersion()){
            throw VersionConflictException.versionConflict();
        }

        if(match.isTimedOut()){
            // La jugada no se guarda: la partida termina por tiempo y gana el rival de quien tenía el turno
            match.finishAndUpdateVersion(opposite(match.getTurn()), EndReason.TIMEOUT.toString());
            saveOrConflict(match, readVersion);
            publisher.publishMatchFinishedMessage(buildMatchFinishedMessage(match));
            throw ClockException.timedOut();
        }

        //La posición se reconstruye desde initialFen y las jugadas guardadas (así se detecta la repetición triple)
        Optional<Applied> applied = ChessRules.apply(match.getInitialFen(), match.playedUciMoves(), movement.uci());
        if(applied.isEmpty()){
            throw MovementNotValidException.illegalMove(movement.uci());
        }

        Applied result = applied.get();
        Movement newMovement = new Movement(
            match.getMovements().size() + 1,
            result.san(),
            movement.uci().trim().toLowerCase(),
            result.fenAfter(),
            Instant.now().truncatedTo(java.time.temporal.ChronoUnit.MILLIS),
            match.getTurn()
        );
        match.addMovement(newMovement, result.turn());

        if(match.getClocks() != null){
            match.getClocks().endTurn(match.getTurn(), turnEndInstant);
        }

        if(result.outcome() != null){
            match.finish(result.outcome().result(), result.outcome().endReason());
        }

        if(match.getDrawOffer() != null){
            match.setDrawOffer(null);
        }

        // Un solo incremento aunque la jugada termine la partida o limpie una oferta (11.4.7)
        match.updateVersion();
        saveOrConflict(match, readVersion);

        if(match.isFinished()){
            publisher.publishMatchFinishedMessage(buildMatchFinishedMessage(match));
        }

        return assembler.toState(match);
    }

    /** El bando indicado se rinde: gana el contrario por "surrender". */
    @PostMapping({"/internal/logic/games/{id}/resign", "/internal/logic/games/{id}/resign/"})
    GameState finishMatch(@PathVariable("id") String id, @RequestBody(required = false) MatchResultRequest body){
        String side = requireSide(body);

        Match match = updateWithRetry(id, current -> {
            requireInProgress(current);
            requireParticipantColor(current, side);
            current.finishAndUpdateVersion(opposite(side), EndReason.SURRENDER.toString());
        });

        publisher.publishMatchFinishedMessage(buildMatchFinishedMessage(match));
        return assembler.toState(match);
    }

    @PostMapping({"/internal/logic/games/{id}/abandon", "/internal/logic/games/{id}/abandon/"})
    ResponseEntity<GameState> abandonMatch(@PathVariable("id") String id, @RequestBody(required = false) MatchResultRequest requestBody){
        String side = requireSide(requestBody);

        Match match = updateWithRetry(id, current -> {
            requireInProgress(current);
            requireParticipantColor(current, side);
            current.finishAndUpdateVersion(opposite(side), EndReason.ABANDONMENT.toString());
        });

        publisher.publishMatchFinishedMessage(buildMatchFinishedMessage(match));
        return ResponseEntity.ok(assembler.toState(match));
    }

    /** drawOffer guarda el color que ofreció tablas (contrato, 11.4.1). */
    @PostMapping({"/internal/logic/games/{id}/draw/offer", "/internal/logic/games/{id}/draw/offer/"})
    ResponseEntity<GameState> offerDraw(@PathVariable("id") String id, @RequestBody(required = false) MatchResultRequest requestBody){
        String side = requireSide(requestBody);

        Match match = updateWithRetry(id, current -> {
            requireInProgress(current);
            if(current.getDrawOffer() != null){
                throw CannotOfferDrawException.alreadyOffered();
            }
            current.setDrawOffer(side);
            current.updateVersion();
        });

        return ResponseEntity.ok(assembler.toState(match));
    }

    /** Solo el rival de quien ofreció puede aceptar (contrato, 11.4.8). */
    @PostMapping({"/internal/logic/games/{id}/draw/accept", "/internal/logic/games/{id}/draw/accept/"})
    ResponseEntity<GameState> acceptDraw(@PathVariable("id") String id, @RequestBody(required = false) MatchResultRequest requestBody){
        String side = requireSide(requestBody);

        Match match = updateWithRetry(id, current -> {
            requireInProgress(current);
            if(current.getDrawOffer() == null){
                throw CannotReplyToDrawException.notOffered(true);
            }
            if(current.getDrawOffer().equals(side)){
                throw CannotReplyToDrawException.notAllowed();
            }
            current.setDrawOffer(null);
            current.finishAndUpdateVersion(Result.DRAW.toString(), EndReason.DRAW.toString());
        });

        publisher.publishMatchFinishedMessage(buildMatchFinishedMessage(match));
        return ResponseEntity.ok(assembler.toState(match));
    }

    /** Solo el rival de quien ofreció puede rechazar. */
    @PostMapping({"/internal/logic/games/{id}/draw/decline", "/internal/logic/games/{id}/draw/decline/"})
    ResponseEntity<GameState> declineDraw(@PathVariable("id") String id, @RequestBody(required = false) MatchResultRequest requestBody){
        String side = requireSide(requestBody);

        Match match = updateWithRetry(id, current -> {
            requireInProgress(current);
            if(current.getDrawOffer() == null){
                throw CannotReplyToDrawException.notOffered(false);
            }
            if(current.getDrawOffer().equals(side)){
                throw CannotReplyToDrawException.notAllowed();
            }
            current.setDrawOffer(null);
            current.updateVersion();
        });

        return ResponseEntity.ok(assembler.toState(match));
    }

    /** Solo quien ofreció puede retirar la oferta. */
    @PostMapping({"/internal/logic/games/{id}/draw/cancel", "/internal/logic/games/{id}/draw/cancel/"})
    ResponseEntity<GameState> cancelDraw(@PathVariable("id") String id, @RequestBody(required = false) MatchResultRequest requestBody){
        String side = requireSide(requestBody);

        Match match = updateWithRetry(id, current -> {
            requireInProgress(current);
            if(current.getDrawOffer() == null){
                throw CannotReplyToDrawException.notOffered(false);
            }
            if(!current.getDrawOffer().equals(side)){
                throw CannotReplyToDrawException.notAllowed();
            }
            current.setDrawOffer(null);
            current.updateVersion();
        });

        return ResponseEntity.ok(assembler.toState(match));
    }

    /** Termina una partida con el reloj vencido (Timeout Worker). */
    @PostMapping({"/internal/logic/games/{id}/timeout", "/internal/logic/games/{id}/timeout/"})
    ResponseEntity<TimeoutResponse> timeoutMatch(@PathVariable("id") String id, @RequestBody(required = false) ExpectedVersionRequestBody requestBody){
        Match match = findMatch(id);

        if(requestBody == null || requestBody.expectedVersion() == null){
            throw RequestNotValidException.notValid("Falta el campo expectedVersion");
        }
        if(match.isFinished()){
            throw GameFinishedException.finished();
        }
        int readVersion = match.getVersion();
        if(readVersion != requestBody.expectedVersion()){
            throw VersionConflictException.versionConflict();
        }
        // Sin reloj, o en waiting (reloj sin iniciar), el reloj no puede haber vencido
        if(!match.isTimedOut()){
            throw ClockException.notTimedOut();
        }

        match.finishAndUpdateVersion(opposite(match.getTurn()), EndReason.TIMEOUT.toString());
        saveOrConflict(match, readVersion);

        publisher.publishMatchFinishedMessage(buildMatchFinishedMessage(match));

        return ResponseEntity.ok(new TimeoutResponse(id, match.getStatus(), match.getResult(), match.getEndReason(), match.getFinishedAt().toString()));
    }

    /** Termina una partida en waiting cuyo plazo venció (Timeout Worker). */
    @PostMapping({"/internal/logic/games/{id}/expire", "/internal/logic/games/{id}/expire/"})
    ResponseEntity<GameState> expireWaitingMatch(@PathVariable("id") String id, @RequestBody(required = false) ExpectedVersionRequestBody requestBody){
        Match match = findMatch(id);

        if(requestBody == null || requestBody.expectedVersion() == null){
            throw RequestNotValidException.notValid("Falta el campo expectedVersion");
        }
        if(match.isFinished()){
            throw GameFinishedException.finished();
        }
        if(!match.isWaiting()){
            throw CannotJoinMatchException.notWaiting();
        }
        int readVersion = match.getVersion();
        if(readVersion != requestBody.expectedVersion()){
            throw VersionConflictException.versionConflict();
        }
        if(!match.isExpiredFromWaiting(properties.waitingTimeout())){
            throw ClockException.waitingNotExpired();
        }

        match.finishAndUpdateVersion(null, EndReason.EXPIRED.toString());
        saveOrConflict(match, readVersion);

        publisher.publishMatchFinishedMessage(buildMatchFinishedMessage(match));

        return ResponseEntity.ok(assembler.toState(match));
    }

    /**
     * Partidas vencidas: in_progress con deadline pasado (reason clock) y waiting con createdAt +
     * WAITING_TIMEOUT_MINUTES pasado (reason waiting). Es la consulta del ciclo de Timeout Worker.
     */
    @GetMapping({"/internal/logic/games/expired", "/internal/logic/games/expired/"})
    ResponseEntity<List<ExpiredQueryResponse>> getExpiredMatches(@RequestParam(name = "limit", required = false) Integer limit){
        if(limit == null || limit < 1){
            throw RequestNotValidException.notValid("limit debe ser un entero mayor que 0");
        }

        List<ExpiredQueryResponse> result = new ArrayList<>();

        for(Match match : repository.findByStatus(Status.IN_PROGRESS.toString())){
            if(result.size() >= limit){
                break;
            }
            if(match.isTimedOut()){
                result.add(new ExpiredQueryResponse(match.getGameId(), match.getVersion(), REASON_CLOCK));
            }
        }

        for(Match match : repository.findByStatus(Status.WAITING.toString())){
            if(result.size() >= limit){
                break;
            }
            if(match.isExpiredFromWaiting(properties.waitingTimeout())){
                result.add(new ExpiredQueryResponse(match.getGameId(), match.getVersion(), REASON_WAITING));
            }
        }

        return ResponseEntity.ok(result);
    }

    @GetMapping({"/internal/logic/games/{id}/analysis-input", "/internal/logic/games/{id}/analysis-input/"})
    ResponseEntity<MatchAnalysis> obtainAnalysisInput(@PathVariable("id") String id){
        Match match = findMatch(id);

        if(!match.isFinished()){
            throw MatchNotFinishedException.notFinished();
        }

        return ResponseEntity.ok(new MatchAnalysis(id, match.getInitialFen(), match.getStatus(), match.getResult(), match.getMovements()));
    }

    /** Cambia la visibilidad. También se admite en partidas terminadas (11.4.6). */
    @PatchMapping({"/internal/logic/games/{id}/visibility", "/internal/logic/games/{id}/visibility/"})
    ResponseEntity<GameState> updateVisibility(@PathVariable("id") String id, @RequestBody(required = false) UpdateVisibilityRequest requestBody){
        Match match = findMatch(id);

        if(requestBody == null || !isVisibility(requestBody.visibility())){
            throw RequestNotValidException.notValid("visibility debe ser \"" + Visibility.PRIVATE + "\" o \"" + Visibility.SHARED + "\"");
        }
        if(requestBody.expectedVersion() == null){
            throw RequestNotValidException.notValid("Falta el campo expectedVersion");
        }
        int readVersion = match.getVersion();
        if(readVersion != requestBody.expectedVersion()){
            throw VersionConflictException.versionConflict();
        }

        match.setVisibility(requestBody.visibility());
        match.updateVersion();
        saveOrConflict(match, readVersion);

        return ResponseEntity.ok(assembler.toState(match));
    }

    /**
     * Paso 1 de la saga de borrado (contrato, 11.4.11). Por partida: leer con su versión, decidir el
     * cierre antes de anonimizar, y guardar cierre y anonimización en una sola escritura atómica.
     * Si pierde la condición, relee y repite. Si otra operación ya la terminó, solo anonimiza.
     */
    @DeleteMapping({"/internal/logic/users/{userId}", "/internal/logic/users/{userId}/"})
    ResponseEntity<Void> anonymizeUser(@PathVariable("userId") String userId){
        List<String> gameIds = repository.findByParticipantsUserId(userId).stream().map(Match::getGameId).toList();

        for(String gameId : gameIds){
            anonymizeInGame(gameId, userId);
        }

        return ResponseEntity.noContent().build();
    }

    private void anonymizeInGame(String gameId, String userId){
        for(int attempt = 0; attempt <= MAX_WRITE_RETRIES; attempt++){
            Optional<Match> found = repository.findByGameId(gameId);
            if(found.isEmpty()){
                return;
            }
            Match match = found.get();
            Participant participant = match.participantWithUserId(userId);
            if(participant == null){
                return; // ya anonimizada: un reintento de la saga no cambia nada
            }
            int readVersion = match.getVersion();

            boolean closesNow = false;
            if(!match.isFinished()){
                closesNow = true;
                if(Mode.MULTIPLAYER.toString().equals(match.getMode()) && Status.IN_PROGRESS.toString().equals(match.getStatus())){
                    // El ganador se decide aquí, antes de anonimizar: el rival del que se borra
                    match.finish(opposite(participant.color()), EndReason.ABANDONMENT.toString());
                }else{
                    match.finish(null, EndReason.ACCOUNT_DELETED.toString());
                }
            }
            match.anonymize(userId);
            match.updateVersion();

            if(store.replaceIfVersion(match, readVersion)){
                if(closesNow){
                    publisher.publishMatchFinishedMessage(buildMatchFinishedMessage(match));
                }
                return;
            }
        }
        throw VersionConflictException.versionConflict();
    }

    @GetMapping({"/health", "/health/"})
    Map<String, String> health(){
        return Map.of("status", "ok");
    }

    // ----------------------------------------------------------------- utilidades

    private Match findMatch(String gameId){
        return repository.findByGameId(gameId).orElseThrow(() -> MatchNotFoundException.notFound(gameId));
    }

    /** Escritura sin expectedVersion: relee, aplica y reintenta hasta 3 veces si pierde la condición. */
    private Match updateWithRetry(String gameId, Change change){
        for(int attempt = 0; attempt <= MAX_WRITE_RETRIES; attempt++){
            Match match = findMatch(gameId);
            int readVersion = match.getVersion();
            change.apply(match);
            if(store.replaceIfVersion(match, readVersion)){
                return match;
            }
        }
        throw VersionConflictException.versionConflict();
    }

    /** Escritura con expectedVersion: si otra escritura ganó la condición, VERSION_CONFLICT. */
    private void saveOrConflict(Match match, int readVersion){
        if(!store.replaceIfVersion(match, readVersion)){
            throw VersionConflictException.versionConflict();
        }
    }

    /** Acciones de juego: en waiting responden GAME_NOT_IN_PROGRESS y en finished, GAME_FINISHED (11.4.6). */
    private static void requireInProgress(Match match){
        if(match.isFinished()){
            throw GameFinishedException.finished();
        }
        if(!match.canBeOperatedOn()){
            throw MatchNotInProgressException.matchNotInProgress();
        }
    }

    private static String requireSide(MatchResultRequest body){
        if(body == null || !isColor(body.side())){
            throw RequestNotValidException.notValid("side debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
        }
        return body.side();
    }

    /** side debe ser un color con participante (11.4.8): en vs_bot, el color del bot no lo es. */
    private static void requireParticipantColor(Match match, String side){
        if(match.participantWithColor(side) == null){
            throw RequestNotValidException.notValid("side debe ser el color de un participante de la partida");
        }
    }

    private MatchFinishedMessage buildMatchFinishedMessage(Match match){
        return new MatchFinishedMessage(UUID.randomUUID().toString(), "game.finished", Instant.now().toString(), match.getGameId(), match.getMatchId(), match.getMode(), match.getParticipants(), match.getResult(), match.getEndReason(), match.getFinishedAt().toString());
    }

    /** Valida el cuerpo de POST /internal/logic/games (11.4.5) y arma la partida nueva. */
    private Match buildNewMatch(CreateMatchRequest request){
        if(request == null){
            throw RequestNotValidException.notValid("Falta el cuerpo de la petición");
        }

        String mode = request.mode();

        if(!Mode.LOCAL.toString().equals(mode) && !Mode.VS_BOT.toString().equals(mode) && !Mode.MULTIPLAYER.toString().equals(mode)){
            throw RequestNotValidException.notValid("mode debe ser \"" + Mode.LOCAL.toString() + "\", \"" + Mode.VS_BOT.toString() + "\" o \"" + Mode.MULTIPLAYER.toString() + "\"");
        }

        if(!isVisibility(request.visibility())){
            throw RequestNotValidException.notValid("visibility debe ser \"" + Visibility.PRIVATE + "\" o \"" + Visibility.SHARED + "\"");
        }

        if(request.timeControl() != null && !Integer.valueOf(10).equals(request.timeControl().minutes())){
            throw RequestNotValidException.notValid("timeControl debe ser null o { \"minutes\": 10 }");
        }

        if(request.participants() == null || request.participants().isEmpty()){
            throw ParticipantsInvalidException.participantsInvalid("Falta información sobre los participantes de la partida");
        }
        for(Participant participant : request.participants()){
            if(participant == null){
                throw ParticipantsInvalidException.participantsInvalid("Hay un participante vacío");
            }
            if(!isColor(participant.color())){
                throw ParticipantsInvalidException.participantsInvalid("El color de los participantes debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
            }
            if(!isUuid(participant.userId())){
                throw ParticipantsInvalidException.participantsInvalid("El userId de cada participante debe ser un UUID");
            }
        }

        Integer botLevel = null;
        String matchId = null;
        String creationKey = null;
        String requestFingerprint = null;
        List<Participant> participants = new ArrayList<>(request.participants());

        if(Mode.LOCAL.toString().equals(mode)){
            if(participants.size() != 2){
                throw ParticipantsInvalidException.participantsInvalid("Una partida en modo local debe tener exactamente 2 participantes");
            }

            if(!participants.get(0).userId().equals(participants.get(1).userId())){
                throw ParticipantsInvalidException.participantsInvalid("En una partida en modo local los 2 participantes deben tener la misma userId");
            }

            if(participants.get(0).color().equals(participants.get(1).color())){
                throw ParticipantsInvalidException.participantsInvalid("Los participantes de la partida deben tener colores distintos");
            }
        }else{
            if(Mode.VS_BOT.toString().equals(mode)){
                botLevel = request.botLevel();

                if(botLevel == null || botLevel < 1 || botLevel > 20){
                    throw RequestNotValidException.notValid("botLevel debe ser un entero de 1 a 20");
                }
            }else{
                if(!isUuid(request.matchId())){
                    throw RequestNotValidException.notValid("matchId debe ser un UUID en partidas multijugador");
                }

                if(request.timeControl() == null){
                    throw RequestNotValidException.notValid("timeControl debe estar presente para partidas en multijugador");
                }

                if(request.creationKey() == null || request.creationKey().isBlank() || request.requestFingerprint() == null || request.requestFingerprint().isBlank()){
                    throw RequestNotValidException.notValid("creationKey y requestFingerprint son obligatorios en partidas multijugador");
                }

                matchId = request.matchId();
                creationKey = request.creationKey();
                requestFingerprint = request.requestFingerprint();
            }

            if(participants.size() != 1){
                throw ParticipantsInvalidException.participantsInvalid("Una partida en modo " + (Mode.VS_BOT.toString().equals(mode) ? "vs bot" : "multijugador") + " debe ser creada con exactamente 1 participante");
            }
        }

        return new Match(mode, request.timeControl(), request.visibility(), botLevel, matchId, creationKey, requestFingerprint, participants);
    }

    private static String opposite(String color){
        return Color.WHITE.toString().equals(color) ? Color.BLACK.toString() : Color.WHITE.toString();
    }

    private static boolean isColor(String value){
        return Color.WHITE.toString().equals(value) || Color.BLACK.toString().equals(value);
    }

    private static boolean isVisibility(String value){
        return Visibility.PRIVATE.toString().equals(value) || Visibility.SHARED.toString().equals(value);
    }

    private static boolean isUuid(String value){
        return value != null && UUID_FORMAT.matcher(value).matches();
    }
}
