package chess;

import java.net.URI;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import chess.ChessRules.Applied;
import chess.constants.Color;
import chess.constants.EndReason;
import chess.constants.Mode;
import chess.constants.Visibility;

@RestController
public class MatchController{
    private static final Pattern UUID_FORMAT = Pattern.compile("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");

    private final MatchRepository repository;
    private final MatchAssembler assembler;

    MatchController(MatchRepository repository, MatchAssembler assembler){
        this.repository = repository;
        this.assembler = assembler;
    }

    /** Crea la partida en la posición inicial. GameLogic genera gameId y createdAt. */
    @PostMapping({"/internal/logic/games", "/internal/logic/games/"})
    ResponseEntity<GameState> newMatch(@RequestBody CreateGameRequest request){
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

    /** Las partidas de un usuario, la más reciente primero. */
    @GetMapping({"/internal/logic/games", "/internal/logic/games/"})
    List<GameSummary> getMatchesByUserId(@RequestParam(name = "userId", required = false) String userId){
        if(userId == null || userId.isBlank()){
            throw new RequestNotValidException("Falta el parámetro userId");
        }

        return repository.findByParticipantsUserIdOrderByCreatedAtDesc(userId).stream().map(assembler::toSummary).toList();
    }

    /** Aplica una jugada UCI sobre la posición guardada. Rechaza las ilegales y las de partidas terminadas. */
    @PostMapping({"/internal/logic/games/{id}/moves", "/internal/logic/games/{id}/moves/"})
    GameState addMovement(@PathVariable("id") String id, @RequestBody MovementCreationEssentials movement){
        Match match = findMatch(id);

        if(movement == null || movement.uci == null || movement.uci.isBlank()){
            throw new RequestNotValidException("Falta el campo uci");
        }
        if(match.isFinished()){
            throw MovementNotValidException.matchFinished();
        }

        //La posición se reconstruye desde initialFen y las jugadas guardadas (así se detecta la repetición triple)
        Optional<Applied> applied = ChessRules.apply(match.getInitialFen(), match.playedUciMoves(), movement.uci);
        if(applied.isEmpty()){
            throw MovementNotValidException.illegalMove(movement.uci);
        }

        Applied result = applied.get();
        Movement newMovement = new Movement(
            match.getMovements().size() + 1,
            result.san(),
            movement.uci.trim().toLowerCase(),
            result.fenAfter(),
            Instant.now().truncatedTo(ChronoUnit.MILLIS)
        );
        match.addMovement(newMovement, result.turn());

        if(result.outcome() != null){
            match.finish(result.outcome().result(), result.outcome().endReason());
        }

        return assembler.toState(repository.save(match));
    }

    /** El bando indicado se rinde: gana el contrario por "surrender". */
    @PostMapping({"/internal/logic/games/{id}/resign", "/internal/logic/games/{id}/resign/"})
    GameState finishMatch(@PathVariable("id") String id, @RequestBody MatchResultRequest body){
        Match match = findMatch(id);

        if(body == null || !isColor(body.side)){
            throw new RequestNotValidException("side debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
        }
        if(match.isFinished()){
            throw MovementNotValidException.matchFinished();
        }

        match.finish(Color.WHITE.toString().equals(body.side) ? Color.BLACK.toString() : Color.WHITE.toString(), EndReason.SURRENDER.toString());

        return assembler.toState(repository.save(match));
    }

    @GetMapping({"/health", "/health/"})
    Map<String, String> health(){
        return Map.of("status", "ok");
    }

    private Match findMatch(String gameId){
        return repository.findByGameId(gameId).orElseThrow(() -> new MatchNotFoundException(gameId));
    }

    /** Valida el cuerpo de POST /internal/logic/games y arma la partida nueva o retorna la partida existente si una con el mismo matchId ya existe. */
    private Match buildNewMatch(CreateGameRequest request){
        if(request == null){
            throw new RequestNotValidException("Falta el cuerpo de la petición");
        }

        String mode = request.mode();

        if(!Mode.LOCAL.toString().equals(mode) && !Mode.VS_BOT.toString().equals(mode) && !Mode.MULTIPLAYER.toString().equals(mode)){
            throw new RequestNotValidException("mode debe ser \"" + Mode.LOCAL.toString() + "\", \"" + Mode.VS_BOT.toString() + "\" o \"" + Mode.MULTIPLAYER.toString() + "\"");
        }

        Integer botLevel = null;
        List<Player> participants = request.participants();
        
        if(Mode.LOCAL.toString().equals(mode)){
            if(participants.size() != 2){
                throw new ParticipantsInvalidException("Una partida en modo local debe tener exactamente 2 participantes");
            }

            if(!participants.get(0).userId().equals(participants.get(1).userId())){
                throw new ParticipantsInvalidException("En una partida en modo local los 2 participantes deben tener la misma userId");
            }

            if(!isColor(participants.get(0).color()) || !isColor(participants.get(1).color())){
                throw new ParticipantsInvalidException("El color de los jugadores debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
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
            }

            if(participants.size() != 1){
                throw new ParticipantsInvalidException("Una partida en modo " + (Mode.VS_BOT.toString().equals(mode) ? "vs bot" : "multijugador") + " debe ser creada con exactamente 1 participante");
            }

            if(!isColor(participants.get(0).color())){
                throw new ParticipantsInvalidException("El color del jugador debe ser \"" + Color.WHITE.toString() + "\" o \"" + Color.BLACK.toString() + "\"");
            }
        }

        if(participants.get(0).userId() == null || !UUID_FORMAT.matcher(participants.get(0).userId()).matches()){
            throw new RequestNotValidException("userId debe ser un UUID");
        }
        
        if(!Visibility.PRIVATE.toString().equals(request.visibility()) && !Visibility.SHARED.toString().equals(request.visibility())){
            throw new RequestNotValidException("visbility debe ser");
        }

        return new Match(mode, request.timeControl(), request.visibility(), botLevel, request.matchId(), participants);
    }

    private static boolean isColor(String value){
        return Color.WHITE.toString().equals(value) || Color.BLACK.toString().equals(value);
    }
}
