package chess;

import java.util.List;
import java.util.Optional;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface MatchRepository extends MongoRepository<Match, String>{
    Optional<Match> findById(String id);
    List<Match> findByWhitePlayerId(Long playerId);
    List<Match> findByBlackPlayerId(Long playerId);
}