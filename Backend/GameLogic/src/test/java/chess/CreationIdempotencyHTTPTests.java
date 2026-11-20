package chess;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
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

/**
 * Idempotencia de POST /internal/logic/games con creationKey + requestFingerprint, tal como los envía
 * Multiplayer (Backend/multiplayer-component/internal/service/service.go). El cuerpo es JSON literal
 * para comprobar el nombre exacto del campo: requestFingerprint (antes se leía requestFingerPrint y
 * llegaba null, lo que provocaba un NullPointerException en el reintento).
 */
@WebMvcTest(MatchController.class)
public class CreationIdempotencyHTTPTests {

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
	private static final String MATCH_ID = "7c0e0b9e-1111-4222-8333-444455556666";
	private static final String KEY = "c2b5f0a6d9e14e0b9a7c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a";

	private static String body(String fingerprint) {
		String fp = fingerprint == null ? "null" : "\"" + fingerprint + "\"";
		return "{\"mode\":\"multiplayer\",\"timeControl\":{\"minutes\":10},\"visibility\":\"private\",\"botLevel\":null,"
			+ "\"matchId\":\"" + MATCH_ID + "\",\"participants\":[{\"userId\":\"" + USER_ID + "\",\"color\":\"white\"}],"
			+ "\"creationKey\":\"" + KEY + "\",\"requestFingerprint\":" + fp + "}";
	}

	private ResultActions create(String fingerprint) throws Exception {
		return mockMvc.perform(post("/internal/logic/games").contentType(MediaType.APPLICATION_JSON).content(body(fingerprint)));
	}

	/** Partida ya guardada con esa creationKey, como la dejaría un primer POST. */
	private Match stored(String fingerprint) {
		Match match = new Match("multiplayer", new TimeControl(10), "private", null, MATCH_ID, KEY, fingerprint,
			List.of(new Participant(USER_ID, "white")));
		when(repository.findByCreationKey(KEY)).thenReturn(Optional.of(match));
		return match;
	}

	@Test
	public void firstCreationReturns201AndStoresTheFingerprintFromTheJsonField() throws Exception {
		when(repository.findByCreationKey(KEY)).thenReturn(Optional.empty());
		ArgumentCaptor<Match> saved = ArgumentCaptor.forClass(Match.class);
		when(repository.save(saved.capture())).thenAnswer(invocation -> invocation.getArgument(0));

		create("fp-1")
			.andExpect(status().isCreated())
			.andExpect(jsonPath("$.matchId").value(MATCH_ID))
			.andExpect(jsonPath("$.status").value("waiting"));

		assertEquals("fp-1", saved.getValue().getRequestFingerPrint(), "requestFingerprint del JSON debe guardarse");
		assertEquals(KEY, saved.getValue().getCreationKey());
	}

	@Test
	public void identicalRetryReturns200WithTheSameGameIdAndDoesNotSaveAgain() throws Exception {
		Match existing = stored("fp-1");

		create("fp-1")
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.gameId").value(existing.getGameId()))
			.andExpect(jsonPath("$.matchId").value(MATCH_ID));

		verify(repository, never()).save(any(Match.class));
	}

	@Test
	public void sameKeyWithDifferentBodyReturns409IdempotencyKeyReused() throws Exception {
		stored("fp-1");

		create("fp-2")
			.andExpect(status().isConflict())
			.andExpect(jsonPath("$.error.code").value("IDEMPOTENCY_KEY_REUSED"));

		verify(repository, never()).save(any(Match.class));
	}

	/** Partidas creadas antes de la corrección: el fingerprint quedó en null. No debe haber NullPointerException (500). */
	@Test
	public void legacyMatchWithNullFingerprintAnswers409InsteadOf500() throws Exception {
		stored(null);

		create("fp-1")
			.andExpect(status().isConflict())
			.andExpect(jsonPath("$.error.code").value("IDEMPOTENCY_KEY_REUSED"));
	}

	@Test
	public void nullFingerprintOnBothSidesIsTreatedAsTheSameRequest() throws Exception {
		Match existing = stored(null);

		create(null)
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.gameId").value(existing.getGameId()));
	}
}
