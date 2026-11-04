package chess;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;
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

/**
 * Partidas sin reloj (timeControl null): así crea el frontend las partidas locales y contra Botcito.
 * Antes, cada jugada respondía 500 (NullPointerException en getClocks().isTimedOut()).
 */
@WebMvcTest(MatchController.class)
public class UntimedMatchHTTPTests {

	@Autowired
	private MockMvc mockMvc;

	@MockitoBean
	private MatchRepository repository;

	@MockitoSpyBean
	private MatchAssembler assembler;

	@MockitoBean
	private RabbitPublisher rabbitPublisher;

	@TestConfiguration
	static class TestConfig {
		@Bean
		public MatchAssembler matchAssembler() {
			return new MatchAssembler();
		}
	}

	private static final String USER_ID = "3f2b8c1e-5a47-4d0e-9b6a-1c2d3e4f5a6b";

	private Match storedUntimedLocalMatch() {
		Match match = new Match("local", null, "private", null, null, null, null,
			List.of(new Participant(USER_ID, "white"), new Participant(USER_ID, "black")));
		match.startClock();
		when(repository.findByGameId(match.getGameId())).thenReturn(Optional.of(match));
		when(repository.save(any(Match.class))).thenAnswer(invocation -> invocation.getArgument(0));
		return match;
	}

	@Test
	public void moveInUntimedMatchSucceeds() throws Exception {
		Match match = storedUntimedLocalMatch();

		mockMvc.perform(post("/internal/logic/games/" + match.getGameId() + "/moves").contentType(MediaType.APPLICATION_JSON)
				.content("{\"uci\":\"e2e4\",\"expectedVersion\":" + match.getVersion() + "}"))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.turn").value("black"))
			.andExpect(jsonPath("$.clocks").doesNotExist());
	}

	@Test
	public void timeoutOnUntimedMatchIsRejectedInsteadOf500() throws Exception {
		Match match = storedUntimedLocalMatch();

		mockMvc.perform(post("/internal/logic/games/" + match.getGameId() + "/timeout").contentType(MediaType.APPLICATION_JSON)
				.content("{\"expectedVersion\":" + match.getVersion() + "}"))
			.andExpect(status().is4xxClientError())
			.andExpect(jsonPath("$.error.code").exists());
	}
}
