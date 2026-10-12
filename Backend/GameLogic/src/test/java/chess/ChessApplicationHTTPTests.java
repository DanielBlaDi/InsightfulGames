package chess;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.restdocs.test.autoconfigure.AutoConfigureRestDocs;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.Mockito.when;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.ArrayList;
import java.util.Optional;

import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

import org.springframework.restdocs.hypermedia.LinksSnippet;

import org.springframework.restdocs.hypermedia.HypermediaDocumentation;

@WebMvcTest(MatchController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
public class ChessApplicationHTTPTests{
	@Autowired
	private MockMvc mockMvc;

	@MockitoBean
	private MatchRepository repository;

	@MockitoSpyBean
	private MatchAssembler assembler;

	@TestConfiguration
    static class TestConfig{
        @Bean
        public MatchAssembler matchAssembler(){
            return new MatchAssembler();
        }
    }
	
	@Test public void shouldReturnNewMatch() throws Exception{
		String requestBody = "{\"whitePlayerId\": -1, \"blackPlayerId\": -1}";

		this.mockMvc.perform(post("/matches").contentType(MediaType.APPLICATION_JSON).content(requestBody))
			.andExpect(status().isCreated())
			.andDo(
				document(
					"createMatch", responseFields(
						fieldWithPath("id").description("The identifier (a String) for the created match."),
						fieldWithPath("whitePlayerId").description("The identifier for the white player of the created match."),
						fieldWithPath("blackPlayerId").description("The identifier for the black player of the created match."),
						fieldWithPath("movements").description("A list of the movements that have been made during this match."),
						fieldWithPath("createdAt").description("The date and time in which this match started."),
						fieldWithPath("result").description("String that describes the end result of this match. Takes one of four values: \"WHITE_WINS\" | \"BLACK_WINS\" | \"DRAW\" | Null (in the case that the Match hasn't ended)"),
						fieldWithPath("resultReason").description("String that describes the reason for the end result of this match. Takes one of five values: \"CHECKMATE\" | \"STALEMATE\" | \"DRAW_RULE\" | \"RESIGNATION\" | Null (in the case that the Match hasn't ended)"),
						subsectionWithPath("_links").description("Links related to this match.")
					)
				)
			);
	}

	@Test public void shouldReturnExistingMatch() throws Exception{
		String testMatchId = "testId";

		when(repository.findById(testMatchId)).thenReturn(Optional.of(new Match(Long.valueOf(-1), Long.valueOf(-1))));

		this.mockMvc.perform(get("/matches/" + testMatchId)).andExpect(status().isOk())
			.andDo(
				document(
					"obtainMatchById", responseFields(
						fieldWithPath("id").description("The identifier (a String) for the requested match, the same that was used on the GET request."),
						fieldWithPath("whitePlayerId").description("The identifier for the white player of the requested match."),
						fieldWithPath("blackPlayerId").description("The identifier for the black player of the requested match."),
						fieldWithPath("movements").description("A list of the movements that have been made during this match."),
						fieldWithPath("createdAt").description("The date and time in which this match started."),
						fieldWithPath("result").description("String that describes the end result of this match, since the match was only just created, it takes the value Null."),
						fieldWithPath("resultReason").description("String that describes the reason for the end result of this match, since the match was only just created, it takes the value Null."),
						subsectionWithPath("_links").description("Links related to this match.")
					)	
				)
			);
	}

	@Test public void shouldReturnExistingMatchesForGivenPlayer() throws Exception{
		final long MOCK_PLAYER_ID = -1;

		ArrayList<Match> mockMatches = new ArrayList<>();
		mockMatches.add(new Match("testId1", Long.valueOf(MOCK_PLAYER_ID), Long.valueOf(-2)));

		when(repository.findByWhitePlayerId(Long.valueOf(MOCK_PLAYER_ID))).thenReturn(mockMatches);

		mockMatches = new ArrayList<>();
		mockMatches.add(new Match("testId2", Long.valueOf(-2), Long.valueOf(MOCK_PLAYER_ID)));

		when(repository.findByBlackPlayerId(Long.valueOf(MOCK_PLAYER_ID))).thenReturn(mockMatches);

		this.mockMvc.perform(get("/players/" + MOCK_PLAYER_ID + "/matches/")).andExpect(status().isOk())
			.andDo(
				document(
					"obtainMatchByPlayerId", responseFields(
						subsectionWithPath("_embedded").description("Autogenerated attribute which holds the response."),
						fieldWithPath("_embedded.matchList").description("A list of the matches that this player has participated in."),
						fieldWithPath("_embedded.matchList[].id").description("The identifier for each of the returned matches."),
						fieldWithPath("_embedded.matchList[].whitePlayerId").description("The identifier for the white player of each of the returned matches."),
						fieldWithPath("_embedded.matchList[].blackPlayerId").description("The identifier for the black player of each of the returned matches."),
						fieldWithPath("_embedded.matchList[].movements").description("A list of the movements that have been made during each of the returned matches."),
						fieldWithPath("_embedded.matchList[].createdAt").description("The date and time in which each of the returned matches started."),
						fieldWithPath("_embedded.matchList[].result").description("String that describes the end result of each of the returned matches. Takes one of four values: \"WHITE_WINS\" | \"BLACK_WINS\" | \"DRAW\" | Null (in the case that the Match hasn't ended)"),
						fieldWithPath("_embedded.matchList[].resultReason").description("String that describes the reason for the end result of each of the returned matches. Takes one of five values: \"CHECKMATE\" | \"STALEMATE\" | \"DRAW_RULE\" | \"RESIGNATION\" | Null (in the case that the Match hasn't ended)"),
						subsectionWithPath("_embedded.matchList[]._links").description("Links related to each of the returned matches."),
						subsectionWithPath("_links").description("Links related to this request.")
					)	
				)
			);
	}
}