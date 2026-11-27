package chess;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;

import chess.matches.Match;
import chess.matches.MatchAssembler;
import chess.matches.MatchController;
import chess.matches.MatchRepository;
import chess.matches.Participant;
import chess.matches.RabbitPublisher;

/** La jugada que termina la partida se guarda (con su evento pendiente) ANTES de publicar game.finished. */
@WebMvcTest(MatchController.class)
public class FinishedEventOrderHTTPTests {

	@Autowired
	private MockMvc mockMvc;

	@MockitoBean
	private MatchRepository repository;

	@MockitoSpyBean
	private MatchAssembler assembler;

	@MockitoBean
	private RabbitPublisher publisher;

	@TestConfiguration
	static class TestConfig {
		@Bean
		public MatchAssembler matchAssembler() {
			return new MatchAssembler();
		}
	}

	private static final String USER_ID = "3f2b8c1e-5a47-4d0e-9b6a-1c2d3e4f5a6b";

	@Test
	public void checkmateIsSavedWithPendingEventBeforePublishing() throws Exception {
		Match match = new Match("local", null, "private", null, null, null, null,
			List.of(new Participant(USER_ID, "white"), new Participant(USER_ID, "black")));
		match.startClock();
		when(repository.findByGameId(match.getGameId())).thenReturn(Optional.of(match));
		ArgumentCaptor<Match> saved = ArgumentCaptor.forClass(Match.class);
		AtomicInteger saves = new AtomicInteger();
		when(repository.save(saved.capture())).thenAnswer(invocation -> {
			saves.incrementAndGet();
			return invocation.getArgument(0);
		});
		// Al publicar una partida terminada, ¿cuántos guardados había ya y estaba guardada terminada?
		List<String> publishedWhen = new java.util.ArrayList<>();
		doAnswer(invocation -> {
			Match m = invocation.getArgument(0);
			if ("finished".equals(m.getStatus())) publishedWhen.add(saves.get() + ":" + saved.getValue().getStatus());
			return null;
		}).when(publisher).publishFinished(any(Match.class));

		String[] foolsMate = {"f2f3", "e7e5", "g2g4", "d8h4"};
		for (String uci : foolsMate) {
			mockMvc.perform(post("/internal/logic/games/" + match.getGameId() + "/moves").contentType(MediaType.APPLICATION_JSON)
					.content("{\"uci\":\"" + uci + "\",\"expectedVersion\":" + match.getVersion() + "}"))
				.andExpect(status().isOk());
		}

		Match last = saved.getValue();
		assertEquals("finished", last.getStatus());
		assertEquals("checkmate", last.getEndReason());
		assertEquals(4, last.getMovements().size());
		assertNotNull(last.getFinishedEventId(), "el evento pendiente se guarda junto con la partida");
		assertEquals(Boolean.FALSE, last.getFinishedEventPublished());

		assertEquals(List.of("4:finished"), publishedWhen, "se publica una sola vez y después del 4.º guardado (el del mate)");
	}

	@Test
	public void resignSavesBeforePublishing() throws Exception {
		Match match = new Match("local", null, "private", null, null, null, null,
			List.of(new Participant(USER_ID, "white"), new Participant(USER_ID, "black")));
		when(repository.findByGameId(match.getGameId())).thenReturn(Optional.of(match));
		when(repository.save(any(Match.class))).thenAnswer(invocation -> invocation.getArgument(0));

		mockMvc.perform(post("/internal/logic/games/" + match.getGameId() + "/resign").contentType(MediaType.APPLICATION_JSON)
				.content("{\"side\":\"white\"}"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.endReason").value("surrender"));

		InOrder order = inOrder(repository, publisher);
		order.verify(repository).save(any(Match.class));
		order.verify(publisher).publishFinished(any(Match.class));
	}
}
