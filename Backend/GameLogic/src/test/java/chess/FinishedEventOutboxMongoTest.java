package chess;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.reset;

import java.net.ConnectException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.amqp.AmqpConnectException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.mongodb.test.autoconfigure.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import chess.matches.FinishedEventRelay;
import chess.matches.Match;
import chess.matches.MatchRepository;
import chess.matches.Participant;
import chess.matches.RabbitPublisher;
import tools.jackson.databind.ObjectMapper;

/**
 * Outbox de game.finished contra MongoDB real (MONGO_TEST_URL). Simula un reinicio: el evento quedó
 * pendiente en la base porque RabbitMQ estaba caído, y un relay nuevo (otro proceso) lo entrega.
 */
@DataMongoTest
@EnabledIfEnvironmentVariable(named = "MONGO_TEST_URL", matches = "mongodb://.+")
public class FinishedEventOutboxMongoTest {

	@DynamicPropertySource
	static void mongo(DynamicPropertyRegistry registry) {
		registry.add("spring.mongodb.uri", () -> System.getenv("MONGO_TEST_URL"));
	}

	@Autowired
	private MatchRepository repository;

	@Autowired
	private MongoTemplate mongo;

	private final RabbitTemplate rabbit = mock(RabbitTemplate.class);
	private final List<String> delivered = new ArrayList<>();

	private static final String A = "3f2b8c1e-5a47-4d0e-9b6a-1c2d3e4f5a6b";

	@BeforeEach
	void clean() {
		repository.deleteAll();
		delivered.clear();
	}

	private Match finishedAndSaved(Instant finishedAt) {
		Match match = new Match("local", null, "private", null, null, null, null,
			List.of(new Participant(A, "white"), new Participant(A, "black")));
		match.finish("black", "checkmate");
		repository.save(match);
		mongo.getCollection("games").updateOne(new Document("_id", match.getGameId()),
			new Document("$set", new Document("finishedAt", java.util.Date.from(finishedAt))));
		return match;
	}

	private void brokerDown() {
		doThrow(new AmqpConnectException(new ConnectException("Connection refused")))
			.when(rabbit).send(eq("game.events"), eq("game.finished"), any(Message.class), any(CorrelationData.class));
	}

	private void brokerUp() {
		reset(rabbit);
		doAnswer(invocation -> {
			delivered.add(((Message) invocation.getArgument(2)).getMessageProperties().getMessageId());
			((CorrelationData) invocation.getArgument(3)).getFuture().complete(new CorrelationData.Confirm(true, null));
			return null;
		}).when(rabbit).send(eq("game.events"), eq("game.finished"), any(Message.class), any(CorrelationData.class));
	}

	private Document raw(String gameId) {
		return mongo.getCollection("games").find(new Document("_id", gameId)).first();
	}

	@Test
	void pendingEventSurvivesBrokerOutageAndIsDeliveredByANewProcess() throws Exception {
		Match match = finishedAndSaved(Instant.now().minusSeconds(60));
		brokerDown();
		new RabbitPublisher(new ObjectMapper(), rabbit, mongo).publishFinished(match);
		assertEquals(false, raw(match.getGameId()).getBoolean("finishedEventPublished"), "sigue pendiente en MongoDB");

		// "Reinicio": instancias nuevas, solo lo guardado en MongoDB.
		brokerUp();
		FinishedEventRelay relay = new FinishedEventRelay(repository, new RabbitPublisher(new ObjectMapper(), rabbit, mongo));
		relay.relayPending();
		Thread.sleep(300);

		assertEquals(List.of(match.getFinishedEventId()), delivered, "se entrega con el mismo eventId");
		assertEquals(true, raw(match.getGameId()).getBoolean("finishedEventPublished"));

		relay.relayPending();
		Thread.sleep(300);
		assertEquals(1, delivered.size(), "ya publicado: no se reenvía");
	}

	@Test
	void legacyFinishedMatchesWithoutOutboxAreNotResent() {
		Match match = finishedAndSaved(Instant.now().minusSeconds(60));
		mongo.getCollection("games").updateOne(new Document("_id", match.getGameId()),
			new Document("$unset", new Document("finishedEventId", "").append("finishedEventPublished", "")));
		brokerUp();

		new FinishedEventRelay(repository, new RabbitPublisher(new ObjectMapper(), rabbit, mongo)).relayPending();

		assertTrue(delivered.isEmpty());
	}

	@Test
	void veryRecentEventsAreLeftToTheImmediateSend() {
		finishedAndSaved(Instant.now());
		brokerUp();

		new FinishedEventRelay(repository, new RabbitPublisher(new ObjectMapper(), rabbit, mongo)).relayPending();

		assertTrue(delivered.isEmpty());
	}
}
