package chess;

import java.util.List;
import java.util.Optional;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface MatchRepository extends MongoRepository<Match, String>{
    Optional<Match> findById(String id);
    /** Las partidas de un usuario, la más reciente primero. */
    List<Match> findByUserIdOrderByCreatedAtDesc(String userId);
}
