package chess;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.http.ResponseEntity;

import com.github.bhlangonijr.chesslib.*;
import com.github.bhlangonijr.chesslib.move.*;

@RestController
public class MatchController{
    private final MatchRepository repository;
    private final MatchAssembler assembler;

    MatchController(MatchRepository repository, MatchAssembler assembler){
        this.repository = repository;
        this.assembler = assembler;
    }

    @PostMapping({"/matches", "/matches/"})
    ResponseEntity<EntityModel<Match>> newMatch(@RequestBody Match newMatch){
        EntityModel<Match> matchEntityModel = assembler.toModel(repository.save(newMatch));

        return ResponseEntity.created(matchEntityModel.getRequiredLink(IanaLinkRelations.SELF).toUri()).body(matchEntityModel);
    }

    @PostMapping({"/movements/{coordinate}", "/movements/{coordinate}/"})
    ResponseEntity<AvailableMovesResponse> getAvailableMovesForPosition(@PathVariable String coordinate, @RequestBody MovementCreationEssentials movement){
        Board board = new Board();
        board.loadFromFen(movement.boardFenBeforeMove);

        List<Move> allLegalMoves = board.legalMoves();
        List<String> availableMovesForSpecificCoordinate = new ArrayList<>();

        for(Move move : allLegalMoves){
            if(move.getFrom().value().equalsIgnoreCase(coordinate)){
                String promotion = move.getPromotion().value();
                availableMovesForSpecificCoordinate.add(move.getTo().value() + (promotion.equals("NONE") ? "" : promotion));
            }
        }

        return ResponseEntity.ok(AvailableMovesResponse.of(availableMovesForSpecificCoordinate));
    }

    @GetMapping({"/matches/{id}", "/matches/{id}/"})
    EntityModel<Match> getMatchById(@PathVariable String id){
        Match foundMatch = repository.findById(id).orElseThrow(() -> new MatchNotFoundException(id));
        return assembler.toModel(foundMatch);
    }

    @GetMapping({"/players/{id}/matches", "/players/{id}/matches/"})
    CollectionModel<EntityModel<Match>> getMatchesByPlayerId(@PathVariable Long id){
        List<EntityModel<Match>> matches = repository.findByWhitePlayerId(id).stream().map(assembler::toModel).collect(Collectors.toList());
        List<EntityModel<Match>> matchesByBlackPlayerId = repository.findByBlackPlayerId(id).stream().map(assembler::toModel).collect(Collectors.toList());
        
        //Avoiding duplicates when the match has the same white player as black player
        matchesByBlackPlayerId.removeAll(matches);
        matches.addAll(matchesByBlackPlayerId);

        return CollectionModel.of(matches, linkTo(methodOn(MatchController.class).getMatchesByPlayerId(id)).withSelfRel());
    }

    /** Cierra la partida y guarda su resultado (mate, tablas o abandono). */
    @PatchMapping({"/matches/{id}/result", "/matches/{id}/result/"})
    ResponseEntity<EntityModel<Match>> finishMatch(@PathVariable String id, @RequestBody MatchResultRequest body){
        Match match = repository.findById(id).orElseThrow(() -> new MatchNotFoundException(id));
        match.finish(body.result(), body.reason());

        return ResponseEntity.ok(assembler.toModel(repository.save(match)));
    }

    @PatchMapping({"/matches/{id}/movements", "/matches/{id}/movements/"})
    ResponseEntity<MovementResponse> addMovement(@PathVariable String id, @RequestBody MovementCreationEssentials movement){
        Match modifiedMatch = repository.findById(id).orElseThrow(() -> new MatchNotFoundException(id));

        if(modifiedMatch.getResult() == null){
            Board board = new Board();
            board.loadFromFen(movement.boardFenBeforeMove);

            Move move = null;
            boolean isLegal = false;
        
            try{
                Move requested = new Move(movement.coordinateNotation, board.getSideToMove());
                for(Move candidate : board.legalMoves()){
                    if(candidate.getFrom() == requested.getFrom()
                            && candidate.getTo() == requested.getTo()
                            && candidate.getPromotion() == requested.getPromotion()){
                        move = candidate;
                        isLegal = true;
                        break;
                    }
                }
            }catch(RuntimeException e){
                isLegal = false; //Notación mal formada
            }

            if(!isLegal){
                throw new MovementNotValidException(movement.boardFenBeforeMove, movement.coordinateNotation);
            }

            board.doMove(move);
            Movement newMovement = new Movement(movement.boardFenBeforeMove, board.getFen(), movement.coordinateNotation, movement.playerId, LocalDateTime.now());

            modifiedMatch.addMovement(newMovement);
            repository.save(modifiedMatch);

            return ResponseEntity.ok(MovementResponse.of(board));
        }else{
            throw new MovementNotValidException("The match is already finished, no more moves can be done.");
        }
    }

    @DeleteMapping({"/matches/{id}", "/matches/{id}/"})
    ResponseEntity<?> deleteMatch(@PathVariable String id){
        repository.deleteById(id);

        return ResponseEntity.noContent().build();
    }
}