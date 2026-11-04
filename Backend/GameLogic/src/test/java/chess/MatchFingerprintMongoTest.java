package chess;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Optional;

import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.mongodb.test.autoconfigure.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import chess.matches.Match;
import chess.matches.MatchRepository;
import chess.matches.Participant;
import chess.matches.TimeControl;

/**
 * Persistencia real de creationKey y requestFingerprint en MongoDB. Necesita un MongoDB en marcha:
 *   MONGO_TEST_URL=mongodb://localhost:27017/games_test ./gradlew test
 * Sin MONGO_TEST_URL la clase se omite (el resto de pruebas no necesita base de datos).
 */
@DataMongoTest
@EnabledIfEnvironmentVariable(named = "MONGO_TEST_URL", matches = "mongodb://.+")
public class MatchFingerprintMongoTest {

	@DynamicPropertySource
	static void mongo(DynamicPropertyRegistry registry) {
		registry.add("spring.mongodb.uri", () -> System.getenv("MONGO_TEST_URL"));
		registry.add("spring.data.mongodb.auto-index-creation", () -> "true");
	}

	@Autowired
	private MatchRepository repository;

	@Autowired
	private MongoTemplate mongo;

	private static final String USER_ID = "3f2b8c1e-5a47-4d0e-9b6a-1c2d3e4f5a6b";

	@BeforeEach
	void clean() {
		repository.deleteAll();
	}

	private static Match multiplayer(String matchId, String key, String fingerprint) {
		return new Match("multiplayer", new TimeControl(10), "private", null, matchId, key, fingerprint,
			List.of(new Participant(USER_ID, "white")));
	}

	@Test
	void fingerprintIsStoredAndReadBackByCreationKey() {
		Match saved = repository.save(multiplayer("7c0e0b9e-1111-4222-8333-444455556666", "key-1", "fp-1"));

		Optional<Match> found = repository.findByCreationKey("key-1");

		assertTrue(found.isPresent());
		assertEquals(saved.getGameId(), found.get().getGameId());
		assertEquals("fp-1", found.get().getRequestFingerPrint());
		Document raw = mongo.getCollection("games").find(new Document("creationKey", "key-1")).first();
		assertEquals("fp-1", raw.getString("requestFingerprint"), "nombre del campo en MongoDB");
	}

	/** Documentos guardados antes de la corrección: el fingerprint no existe o es null; se leen sin error. */
	@Test
	void legacyDocumentWithoutFingerprintReadsAsNull() {
		repository.save(multiplayer("7c0e0b9e-1111-4222-8333-444455557777", "legacy-key", null));
		mongo.getCollection("games").updateOne(new Document("creationKey", "legacy-key"),
			new Document("$unset", new Document("requestFingerprint", "")));

		Optional<Match> found = repository.findByCreationKey("legacy-key");

		assertTrue(found.isPresent());
		assertNull(found.get().getRequestFingerPrint());
	}
}
