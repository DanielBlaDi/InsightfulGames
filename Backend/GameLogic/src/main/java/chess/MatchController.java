package chess;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.http.HttpStatus;
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

    @GetMapping("/matches/{id}")
    EntityModel<Match> getMatchById(@PathVariable String id){
        Match foundMatch = repository.findById(id).orElseThrow(() -> new MatchNotFoundException(id));
        return assembler.toModel(foundMatch);
    }

    @PostMapping("/matches")
    ResponseEntity<EntityModel<Match>> newMatch(@RequestBody Match newMatch){
        EntityModel<Match> matchEntityModel = assembler.toModel(repository.save(newMatch));

        return ResponseEntity.created(matchEntityModel.getRequiredLink(IanaLinkRelations.SELF).toUri()).body(matchEntityModel);
    }

    @GetMapping("/players/{id}/matches/")
    CollectionModel<EntityModel<Match>> getMatchesByPlayerId(@PathVariable Long id){
        List<EntityModel<Match>> matches = repository.findByWhitePlayerId(id).stream().map(assembler::toModel).collect(Collectors.toList());
        matches.addAll(repository.findByBlackPlayerId(id).stream().map(assembler::toModel).collect(Collectors.toList()));
        return CollectionModel.of(matches, linkTo(methodOn(MatchController.class).getMatchesByPlayerId(id)).withSelfRel());
    }

    @PatchMapping("/matches/{id}/movements/")
    ResponseEntity<String> addMovement(@PathVariable String id, @RequestBody MovementCreationEssentials movement){
        Match modifiedMatch = repository.findById(id).orElseThrow(() -> new MatchNotFoundException(id));
        Movement newMovement = null;

        Board board = new Board();
        board.loadFromFen(movement.boardFenBeforeMove);

        if(board.isMoveLegal(new Move(movement.coordinateNotation, board.getSideToMove()), true)){
            board.doMove(new Move(movement.coordinateNotation, board.getSideToMove()));
            String boardFenAfterMove = board.getFen();
            newMovement = new Movement(movement.boardFenBeforeMove, boardFenAfterMove, movement.coordinateNotation, movement.playerId, LocalDateTime.now());
            
            modifiedMatch.addMovement(newMovement);
        }else{
            throw new MovementNotValidException(movement.boardFenBeforeMove, movement.coordinateNotation);
        }

        repository.save(modifiedMatch);

        return ResponseEntity.status(HttpStatus.OK).body("{updatedFen: \"" + newMovement.getBoardFenAfterMove() + "\", matchStatus: " + newMovement.getBoardStatusAfterMove() + "}");
    }
}