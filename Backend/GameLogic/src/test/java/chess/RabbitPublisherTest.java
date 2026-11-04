package chess;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;

import java.net.ConnectException;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.AmqpConnectException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

import chess.matches.RabbitPublisher;
import tools.jackson.databind.ObjectMapper;

/** Con RabbitMQ caído, terminar una partida no debe fallar la petición: el evento se reintenta. */
class RabbitPublisherTest {

	@Test
	void brokerDownDoesNotThrowAndRetries() {
		RabbitTemplate template = mock(RabbitTemplate.class);
		doThrow(new AmqpConnectException(new ConnectException("Connection refused")))
			.when(template).send(eq("game.events"), eq("game.finished"), any(Message.class), any(CorrelationData.class));
		RabbitPublisher publisher = new RabbitPublisher(new ObjectMapper(), template);
		Message message = MessageBuilder.withBody("{}".getBytes()).build();

		assertDoesNotThrow(() -> invokeSend(publisher, message));

		// Primer intento inmediato y reintento tras 1 s.
		verify(template, timeout(3000).times(2)).send(eq("game.events"), eq("game.finished"), any(Message.class), any(CorrelationData.class));
	}

	private static void invokeSend(RabbitPublisher publisher, Message message) throws Exception {
		var method = RabbitPublisher.class.getDeclaredMethod("sendWithRetry", Message.class, String.class, int.class);
		method.setAccessible(true);
		method.invoke(publisher, message, "evt-1", 0);
	}
}
