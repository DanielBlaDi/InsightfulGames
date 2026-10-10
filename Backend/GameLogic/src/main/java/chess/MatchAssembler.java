package chess;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.*;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class MatchAssembler implements RepresentationModelAssembler<Match, EntityModel<Match>>{
    @Override public EntityModel<Match> toModel(Match match){
        return EntityModel.of(match, linkTo(methodOn(MatchController.class).getMatchById(match.getId())).withSelfRel());
    }
}