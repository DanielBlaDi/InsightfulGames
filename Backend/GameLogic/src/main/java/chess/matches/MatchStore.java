package chess.matches;

import static org.springframework.data.mongodb.core.query.Criteria.where;
import static org.springframework.data.mongodb.core.query.Query.query;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

/**
 * Escrituras de partidas (contrato, 11.4.7): toda escritura de una partida existente es una
 * actualización atómica condicionada por _id y por la versión leída. No se usa save sin condición.
 */
@Component
public class MatchStore{
    private final MongoTemplate template;

    public MatchStore(MongoTemplate template){
        this.template = template;
    }

    /** Inserta una partida nueva. Un índice único violado lanza DuplicateKeyException. */
    public Match insert(Match match){
        return template.insert(match);
    }

    /**
     * Reemplaza el documento solo si su versión sigue siendo readVersion. match ya trae la versión
     * nueva (readVersion + 1). Devuelve false si otra escritura ganó la condición.
     */
    public boolean replaceIfVersion(Match match, int readVersion){
        Match previous = template.findAndReplace(
            query(where("_id").is(match.getGameId()).and("version").is(readVersion)),
            match);
        return previous != null;
    }
}
