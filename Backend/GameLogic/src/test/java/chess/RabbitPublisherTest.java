package chess;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import java.net.ConnectException;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.AmqpConnectException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.ReturnedMessage;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import chess.matches.Match;
import chess.matches.Participant;
import chess.matches.RabbitPublisher;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * game.finished sale del outbox de la partida: lleva eventId en el cuerpo, no lanza si RabbitMQ está
 * caído y solo se marca como publicado con la confirmación (ack) del broker.
 */
class RabbitPublisherTest {

	private static final String A = "3f2b8c1e-5a47-4d0e-9b6a-1c2d3e4f5a6b";
	private static final String B = "4f2b8c1e-5a47-4d0e-9b6a-1c2d3e4f5a6c";

	private final RabbitTemplate rabbit = mock(RabbitTemplate.class);
	private final MongoTemplate mongo = mock(MongoTemplate.class);
	private final ObjectMapper json = new ObjectMapper();
	private final RabbitPublisher publisher = new RabbitPublisher(json, rabbit, mongo);

	private static Match finishedMatch() {
		Match match = new Match("multiplayer", null, "private", null, "7c0e0b9e-1111-4222-8333-444455556666", null, null,
			new java.util.ArrayList<>(List.of(new Participant(A, "white"))));
		match.addParticipant(new Participant(B, "black"));
		match.finish("white", "checkmate");
		return match;
	}

	/** Simula la respuesta del broker a la confirmación del envío. */
	private void brokerAnswers(boolean ack, boolean returned, AtomicReference<Message> sent) {
		doAnswer(invocation -> {
			Message message = invocation.getArgument(2);
			CorrelationData correlation = invocation.getArgument(3);
			if (sent != null) sent.set(message);
			if (returned) correlation.setReturned(new ReturnedMessage(message, 312, "NO_ROUTE", "game.events", "game.finished"));
			correlation.getFuture().complete(new CorrelationData.Confirm(ack, ack ? null : "nack"));
			return null;
		}).when(rabbit).send(eq("game.events"), eq("game.finished"), any(Message.class), any(CorrelationData.class));
	}

	@Test
	void bodyCarriesTheStableEventIdTheConsumersRequire() throws Exception {
		Match match = finishedMatch();
		AtomicReference<Message> sent = new AtomicReference<>();
		brokerAnswers(true, false, sent);

		publisher.publishFinished(match);

		JsonNode body = json.readTree(sent.get().getBody());
		assertEquals(match.getFinishedEventId(), body.get("eventId").asString());
		assertTrue(body.get("eventId").asString().matches("[0-9a-f-]{36}"));
		assertEquals("game.finished", body.get("eventType").asString());
		assertEquals(match.getGameId(), body.get("gameId").asString());
		assertEquals("multiplayer", body.get("mode").asString());
		assertEquals(2, body.get("participants").size());
		assertEquals(match.getFinishedEventId(), sent.get().getMessageProperties().getMessageId());
	}

	@Test
	void ackMarksTheEventAsPublished() {
		brokerAnswers(true, false, null);
		publisher.publishFinished(finishedMatch());
		verify(mongo).updateFirst(any(Query.class), any(Update.class), eq(Match.class));
	}

	@Test
	void nackOrUnroutableLeavesTheEventPending() {
		brokerAnswers(false, false, null);
		publisher.publishFinished(finishedMatch());
		brokerAnswers(true, true, null);
		publisher.publishFinished(finishedMatch());
		verify(mongo, never()).updateFirst(any(Query.class), any(Update.class), eq(Match.class));
	}

	@Test
	void brokerDownDoesNotThrowAndLeavesTheEventPending() {
		doThrow(new AmqpConnectException(new ConnectException("Connection refused")))
			.when(rabbit).send(eq("game.events"), eq("game.finished"), any(Message.class), any(CorrelationData.class));

		assertDoesNotThrow(() -> publisher.publishFinished(finishedMatch()));
		verifyNoInteractions(mongo);
	}

	@Test
	void matchWithoutPendingEventSendsNothing() {
		Match ongoing = new Match("local", null, "private", null, null, null, null,
			List.of(new Participant(A, "white"), new Participant(A, "black")));
		publisher.publishFinished(ongoing);
		verifyNoInteractions(rabbit);
	}

	@Test
	void eventIdIsKeptIfFinishIsCalledAgain() {
		Match match = finishedMatch();
		String first = match.getFinishedEventId();
		match.finish("white", "checkmate");
		assertEquals(first, match.getFinishedEventId());
	}
}
