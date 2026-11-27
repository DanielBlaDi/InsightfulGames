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
import org.springframework.test.web.servlet.ResultActions;

import chess.matches.Match;
import chess.matches.MatchAssembler;
import chess.matches.MatchController;
import chess.matches.MatchRepository;
import chess.matches.Participant;
import chess.matches.RabbitPublisher;
import chess.matches.TimeControl;

/** drawOffer es el color de quien ofrece tablas; solo el rival acepta o rechaza y solo quien ofreció cancela. */
@WebMvcTest(MatchController.class)
public class DrawOfferHTTPTests {

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

	private Match inProgress() {
		Match match = new Match("multiplayer", new TimeControl(10), "private", null, "7c0e0b9e-1111-4222-8333-444455556666", null, null,
			new java.util.ArrayList<>(List.of(new Participant("3f2b8c1e-5a47-4d0e-9b6a-1c2d3e4f5a6b", "white"))));
		match.addParticipant(new Participant("4f2b8c1e-5a47-4d0e-9b6a-1c2d3e4f5a6c", "black"));
		match.setStatus("in_progress");
		match.startClock();
		when(repository.findByGameId(match.getGameId())).thenReturn(Optional.of(match));
		when(repository.save(any(Match.class))).thenAnswer(invocation -> invocation.getArgument(0));
		return match;
	}

	private ResultActions draw(Match match, String op, String side) throws Exception {
		return mockMvc.perform(post("/internal/logic/games/" + match.getGameId() + "/draw/" + op)
			.contentType(MediaType.APPLICATION_JSON).content("{\"side\":\"" + side + "\"}"));
	}

	@Test
	public void offerStoresTheOfferingColor() throws Exception {
		Match match = inProgress();
		draw(match, "offer", "white").andExpect(status().isOk()).andExpect(jsonPath("$.drawOffer").value("white"));
	}

	@Test
	public void onlyTheOpponentCanAccept() throws Exception {
		Match match = inProgress();
		draw(match, "offer", "white").andExpect(status().isOk());
		draw(match, "accept", "white").andExpect(status().is4xxClientError());
		draw(match, "accept", "black").andExpect(status().isOk())
			.andExpect(jsonPath("$.status").value("finished"))
			.andExpect(jsonPath("$.result").value("draw"));
	}

	@Test
	public void opponentDeclinesAndOffererCancels() throws Exception {
		Match match = inProgress();
		draw(match, "offer", "black").andExpect(status().isOk()).andExpect(jsonPath("$.drawOffer").value("black"));
		draw(match, "decline", "black").andExpect(status().is4xxClientError());
		draw(match, "decline", "white").andExpect(status().isOk()).andExpect(jsonPath("$.drawOffer").doesNotExist());
		draw(match, "offer", "white").andExpect(status().isOk());
		draw(match, "cancel", "black").andExpect(status().is4xxClientError());
		draw(match, "cancel", "white").andExpect(status().isOk()).andExpect(jsonPath("$.drawOffer").doesNotExist());
	}
}
