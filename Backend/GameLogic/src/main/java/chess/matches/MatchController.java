package chess.matches;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
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
import chess.matches.ChessRules.Applied;
import chess.movements.Movement;
import chess.movements.MovementCreationEssentials;
import chess.movements.MovementNotValidException;

@RestController
public class MatchController{
    private static final Pattern UUID_FORMAT = Pattern.compile("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");

    private final MatchRepository repository;
    private final MatchAssembler assembler;
    private final RabbitTemplate rabbitTemplate;

    MatchController(MatchRepository repository, MatchAssembler assembler, RabbitTemplate rabbitTemplate){
        this.repository = repository;
        this.assembler = assembler;
        this.rabbitTemplate = rabbitTemplate;
    }

    /** Crea la partida en la posición inicial. GameLogic genera gameId y createdAt. */
    @PostMapping({"/internal/logic/games", "/internal/logic/games/"})
    ResponseEntity<GameState> newMatch(@RequestBody CreateMatchRequest request){
        Match saved = null;
        boolean matchAlreadyExists = false;

        if(request.matchId() != null){
            Optional<Match> alreadyExistingMatch = repository.findByMatchId(request.matchId());
                
            if(alreadyExistingMatch.isPresent()){
                saved = alreadyExistingMatch.get();
                matchAlreadyExists = true;
            }
        }
        
        if(matchAlreadyExists){
            return ResponseEntity.ok(assembler.toState(saved));
        }else{
            saved = repository.save(buildNewMatch(request));

            return ResponseEntity.created(URI.create("/internal/logic/games/" + saved.getGameId())).body(assembler.toState(saved));
        }
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
            throw new MatchNotFoundException(matchId);
        }
    }

    /** Las partidas de un usuario, la más reciente primero. */
    @GetMapping({"/internal/logic/games", "/internal/logic/games/"})
    ResponseEntity<GamesPage> getMatchesByUserIdPaged(@RequestParam(name = "userId", required = false) String userId, @RequestParam(name = "limit", required = false) Integer limit, @RequestParam(name = "cursor", required = false) String cursor){
        if(userId == null || userId.isBlank()){
            throw new RequestNotValidException("Falta el parámetro userId");
        }

        if(limit == null){
            limit = 20;
        }else if(limit > 20 || limit < 1){
            throw new RequestNotValidException("El parámetro limit debe ser un valor entre 1 y 20 inclusivos");
        }

        List<GameSummary> matchList = repository.findByParticipantsUserIdOrderByCreatedAtDesc(userId).stream().map(assembler::toSummary).toList();

        GamesPage result;
        int decodedCursor;

        if(cursor == null){
            decodedCursor = 1;
        }else{
            decodedCursor = Integer.parseInt(new String(Base64.getUrlDecoder().decode(cursor), StandardCharsets.UTF_8));
        }

        if(matchList.size() > limit*decodedCursor){
            String encodedResponseCursor = Base64.getUrlEncoder().withoutPadding().encodeToString(String.valueOf(decodedCursor + 1).getBytes(StandardCharsets.UTF_8));
            result = new GamesPage(matchList.subList(limit * (decodedCursor - 1), (limit * decodedCursor)), encodedResponseCursor);
        }else if(matchList.size() == limit*decodedCursor){
            result = new GamesPage(matchList.subList(limit * (decodedCursor - 1), (limit * decodedCursor)), null);
        }else{
            result = new GamesPage(matchList.subList(limit * (decodedCursor - 1), matchList.size()), null);
        }

        return ResponseEntity.ok(result);
    }

    @PostMapping({"/internal/logic/games/{id}/join", "/internal/logic/games/{id}/join/"})
    ResponseEntity<GameState> joinMatch(@PathVariable("id") String id, @RequestBody JoinMatchRequestBody requestBody){
        Match foundMatch = findMatch(id);

        if(!foundMatch.getStatus().equals(Status.WAITING.toString())){
            throw new CannotJoinMatchException(id, "GAME_NOT_WAITING");
        }

        List<Participant> participants = foundMatch.getParticipants();
        String remainingColor = "";

        for(int i=0; i<participants.size(); i++){
            if(participants.get(i).userId().equals(requestBody.userId())){
                throw new CannotJoinMatchException(id, "ALREADY_PARTICIPANT");
            }else{
                remainingColor = participants.get(i).color().equals(Color.BLACK.toString()) ? Color.WHITE.toString() : Color.BLACK.toString();
            }
        }

        foundMatch.addParticipant(new Participant(requestBody.userId(), remainingColor));
        foundMatch.setStatus(Status.IN_PROGRESS.toString());
        
        if(foundMatch.getTimeControl() != null){
            Clocks clock = foundMatch.getClocks();
            Instant turnStart = Instant.now();

            clock.setTurnStartedAt(turnStart.toString());
            clock.setDeadline(turnStart.plusMillis(clock.getWhite()).toString());
        }

        repository.save(foundMatch);

        return ResponseEntity.ok(assembler.toState(foundMatch));
    }


    /** Aplica una jugada UCI sobre la posición guardada. Rechaza las ilegales y las de partidas terminadas. */
    @PostMapping({"/internal/logic/games/{id}/moves", "/internal/logic/games/{id}/moves/"})
    GameState addMovement(@PathVariable("id") String id, @RequestBody MovementCreationEssentials movement){
        Match match = findMatch(id);

        if(movement == null || movement.uci() == null || movement.uci().isBlank()){
            throw new RequestNotValidException("Falta el campo uci");
        }
        if(!match.canBeOperatedOn()){
            throw MatchNotInProgressException.matchNotInProgress();
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
            Instant.now().truncatedTo(ChronoUnit.MILLIS),
            match.getTurn()
        );
        match.addMovement(newMovement, result.turn());

        if(result.outcome() != null){
            match.finish(result.outcome().result(), result.outcome().endReason());
        }

        if(match.getDrawOffer() != null){
            match.setDrawOffer(null);
        }

        return assembler.toState(repository.save(match));
    }

    /** El bando indicado se rinde: gana el contrario por "surrender". */
    @PostMapping({"/internal/logic/games/{id}/resign", "/internal/logic/games/{id}/resign/"})
    GameState finishMatch(@PathVariable("id") String id, @RequestBody MatchResultRequest body){
        Match match = findMatch(id);

        if(body == null || !isColor(body.side())){
            throw new RequestNotValidException("side debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
        }
        if(!match.canBeOperatedOn()){
            throw MatchNotInProgressException.matchNotInProgress();
        }

        match.finish(Color.WHITE.toString().equals(body.side()) ? Color.BLACK.toString() : Color.WHITE.toString(), EndReason.SURRENDER.toString());

        return assembler.toState(repository.save(match));
    }

    @PostMapping({"/internal/logic/games/{id}/abandon", "/internal/logic/games/{id}/abandon/"})
    ResponseEntity<GameState> abandonMatch(@PathVariable("id") String id, @RequestBody MatchResultRequest requestBody){
        Match match = findMatch(id);

        if(requestBody == null || !isColor(requestBody.side())){
            throw new RequestNotValidException("side debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
        }

        if(!match.canBeOperatedOn()){
            throw MatchNotInProgressException.matchNotInProgress();
        }

        match.finish(Color.WHITE.toString().equals(requestBody.side()) ? Color.BLACK.toString() : Color.WHITE.toString(), EndReason.ABANDONMENT.toString());

        return ResponseEntity.ok(assembler.toState(repository.save(match)));
    }

    @PostMapping({"/internal/logic/games/{id}/draw/offer", "/internal/logic/games/{id}/draw/offer/"})
    ResponseEntity<GameState> offerDraw(@PathVariable("id") String id, @RequestBody MatchResultRequest requestBody){
        Match match = findMatch(id);

        if(requestBody == null || !isColor(requestBody.side())){
            throw new RequestNotValidException("side debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
        }

        if(!match.canBeOperatedOn()){
            throw MatchNotInProgressException.matchNotInProgress();
        }

        if(match.getDrawOffer() != null){
            throw CannotOfferDrawException.alreadyOffered();
        }

        match.setDrawOffer(Color.WHITE.toString().equals(requestBody.side()) ? Color.BLACK.toString() : Color.WHITE.toString());

        return ResponseEntity.ok(assembler.toState(repository.save(match)));
    }

    @PostMapping({"/internal/logic/games/{id}/draw/accept", "/internal/logic/games/{id}/draw/accept/"})
    ResponseEntity<GameState> acceptDraw(@PathVariable("id") String id, @RequestBody MatchResultRequest requestBody){
        Match match = findMatch(id);

        if(requestBody == null || !isColor(requestBody.side())){
            throw new RequestNotValidException("side debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
        }

        if(!match.canBeOperatedOn()){
            throw MatchNotInProgressException.matchNotInProgress();
        }

        if(match.getDrawOffer() == null){
            throw CannotReplyToDrawException.notOffered(true);
        }

        if(match.getDrawOffer().equals(requestBody.side())){
            throw CannotReplyToDrawException.notAllowed();
        }

        match.finish(Result.DRAW.toString(), EndReason.DRAW.toString());

        return ResponseEntity.ok(assembler.toState(repository.save(match)));
    }

    @PostMapping({"/internal/logic/games/{id}/draw/decline", "/internal/logic/games/{id}/draw/decline/"})
    ResponseEntity<GameState> declineDraw(@PathVariable("id") String id, @RequestBody MatchResultRequest requestBody){
        Match match = findMatch(id);

        if(requestBody == null || !isColor(requestBody.side())){
            throw new RequestNotValidException("side debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
        }

        if(!match.canBeOperatedOn()){
            throw MatchNotInProgressException.matchNotInProgress();
        }

        if(match.getDrawOffer() == null){
            throw CannotReplyToDrawException.notOffered(false);
        }

        if(match.getDrawOffer().equals(requestBody.side())){
            throw CannotReplyToDrawException.notAllowed();
        }

        match.setDrawOffer(null);

        return ResponseEntity.ok(assembler.toState(repository.save(match)));
    }

    @PostMapping({"/internal/logic/games/{id}/draw/cancel", "/internal/logic/games/{id}/draw/cancel/"})
    ResponseEntity<GameState> cancelDraw(@PathVariable("id") String id, @RequestBody MatchResultRequest requestBody){
        Match match = findMatch(id);

        if(requestBody == null || !isColor(requestBody.side())){
            throw new RequestNotValidException("side debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
        }

        if(!match.canBeOperatedOn()){
            throw MatchNotInProgressException.matchNotInProgress();
        }

        if(match.getDrawOffer() == null){
            throw CannotReplyToDrawException.notOffered(false);
        }

        if(!match.getDrawOffer().equals(requestBody.side())){
            throw CannotReplyToDrawException.notAllowed();
        }

        match.setDrawOffer(null);

        return ResponseEntity.ok(assembler.toState(repository.save(match)));
    }
 
    @PatchMapping({"/internal/logic/games/{id}/visibility", "/internal/logic/games/{id}/visibility/"})
    private ResponseEntity<GameState> updateVisibility(@PathVariable("id") String id, @RequestBody UpdateVisibilityRequest requestBody){
        Match foundMatch = findMatch(id);

        foundMatch.setVisibility(requestBody.visibility());

        repository.save(foundMatch);

        return ResponseEntity.ok(assembler.toState(foundMatch));
    }

    @DeleteMapping({"/internal/logic/users/{userId}", "/internal/logic/users/{userId}/"})
    private ResponseEntity<Void> anonymizeUser(@PathVariable("userId") String userId){
        List<Match> userMatches = repository.findByParticipantsUserId(userId);

        for(Match match : userMatches){
            List<Participant> participants = match.getParticipants();
            for(Participant participant : participants){
                if(participant.userId().equals(userId)){
                    if(match.getStatus().equals(Status.IN_PROGRESS.toString()) && match.getMode().equals(Mode.MULTIPLAYER.toString())){
                        match.finish(Color.WHITE.toString().equals(participant.color()) ? Color.BLACK.toString() : Color.WHITE.toString(), EndReason.ABANDONMENT.toString());

                        match.anonymizeUser(userId);

                        repository.save(match);

                        rabbitTemplate.convertAndSend(
                            "game.events", 
                            "game.finished", 
                            new MatchFinishedMessage(
                                UUID.randomUUID().toString(), 
                                "game.finished", 
                                Instant.now().toString(), 
                                match.getGameId(), 
                                match.getMatchId(), 
                                match.getMode(), 
                                participants, 
                                match.getResult(), 
                                match.getEndReason(), 
                                match.getFinishedAt().toString()
                            )
                        );
                    }else{
                        if(match.getStatus().equals(Status.WAITING.toString()) || match.getMode().equals(Mode.LOCAL.toString()) || match.getMode().equals(Mode.VS_BOT.toString())){
                            match.finish(null, EndReason.ACCOUNT_DELETED.toString());
                        }
                        
                        match.anonymizeUser(userId);

                        repository.save(match);
                    }
                }
            }

            
        }

        return ResponseEntity.noContent().build();
    }

    @GetMapping({"/health", "/health/"})
    Map<String, String> health(){
        return Map.of("status", "ok");
    }

    private Match findMatch(String gameId){
        return repository.findByGameId(gameId).orElseThrow(() -> new MatchNotFoundException(gameId));
    }

    /** Valida el cuerpo de POST /internal/logic/games y arma la partida nueva o retorna la partida existente si una con el mismo matchId ya existe. */
    private Match buildNewMatch(CreateMatchRequest request){
        if(request == null){
            throw new RequestNotValidException("Falta el cuerpo de la petición");
        }

        String mode = request.mode();

        if(!Mode.LOCAL.toString().equals(mode) && !Mode.VS_BOT.toString().equals(mode) && !Mode.MULTIPLAYER.toString().equals(mode)){
            throw new RequestNotValidException("mode debe ser \"" + Mode.LOCAL.toString() + "\", \"" + Mode.VS_BOT.toString() + "\" o \"" + Mode.MULTIPLAYER.toString() + "\"");
        }

        if(!Visibility.PRIVATE.toString().equals(request.visibility()) && !Visibility.SHARED.toString().equals(request.visibility())){
            throw new RequestNotValidException("visibility debe ser \"" + Visibility.PRIVATE + "\" o \"" + Visibility.SHARED + "\"");
        }

        if(request.participants() == null){
            throw new ParticipantsInvalidException("Falta información sobre los participantes de la partida");
        }

        Integer botLevel = null;
        List<Participant> participants = request.participants();
        
        if(Mode.LOCAL.toString().equals(mode)){
            if(participants.size() != 2){
                throw new ParticipantsInvalidException("Una partida en modo local debe tener exactamente 2 participantes");
            }

            if(!participants.get(0).userId().equals(participants.get(1).userId())){
                throw new ParticipantsInvalidException("En una partida en modo local los 2 participantes deben tener la misma userId");
            }

            if(!isColor(participants.get(0).color()) || !isColor(participants.get(1).color())){
                throw new ParticipantsInvalidException("El color de los participantes debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
            }

            if(participants.get(0).color().equals(participants.get(1).color())){
                throw new ParticipantsInvalidException("Los participantes de la partida deben tener colores distintos");
            }
        }else{
            if(Mode.VS_BOT.toString().equals(mode)){
                botLevel = request.botLevel();

                if(botLevel == null || botLevel < 1 || botLevel > 20){
                    throw new RequestNotValidException("botLevel debe ser un entero de 1 a 20");
                }
            }else{
                if(request.matchId() == null){
                    throw new RequestNotValidException("matchId debe estar presente para partidas en multijugador");
                }

                if(request.timeControl() == null){
                    throw new RequestNotValidException("timeControl debe estar presente para partidas en multijugador");
                }
            }

            if(participants.size() != 1){
                throw new ParticipantsInvalidException("Una partida en modo " + (Mode.VS_BOT.toString().equals(mode) ? "vs bot" : "multijugador") + " debe ser creada con exactamente 1 participante");
            }

            if(!isColor(participants.get(0).color())){
                throw new ParticipantsInvalidException("El color del jugador debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
            }
        }

        //The check is performed here, because at this point, the number of participants has been confirmed, and in local matches, both userId have been confirmed to be equal, so checking only the first one works for every case
        if(participants.get(0).userId() == null || !UUID_FORMAT.matcher(participants.get(0).userId()).matches()){
            throw new RequestNotValidException("userId debe ser un UUID");
        }
        
        return new Match(mode, request.timeControl(), request.visibility(), botLevel, request.matchId(), participants);
    }

    private static boolean isColor(String value){
        return Color.WHITE.toString().equals(value) || Color.BLACK.toString().equals(value);
    }
}
