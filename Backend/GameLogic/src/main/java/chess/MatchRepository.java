package chess;

import java.util.List;
import java.util.Optional;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface MatchRepository extends MongoRepository<Match, String>{
    Optional<Match> findByGameId(String gameId);
    Optional<Match> findByMatchId(String matchId);
    /** Las partidas de un usuario, la más reciente primero. */
    List<Match> findByParticipantsUserIdOrderByCreatedAtDesc(String userId);
    List<Match> findByParticipantsUserIdAndStatus(String userId, String status);
}
