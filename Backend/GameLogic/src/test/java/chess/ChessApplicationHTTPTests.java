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

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.restdocs.hypermedia.LinksSnippet;
import org.springframework.restdocs.payload.PayloadDocumentation;
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

	private String testMatchId;
	
	@Test public void shouldReturnNewMatch() throws Exception{
		String requestBody = "{\"whitePlayerId\": -1, \"blackPlayerId\": -1}";

		String responseBody = this.mockMvc.perform(post("/matches").contentType(MediaType.APPLICATION_JSON).content(requestBody))
			.andExpect(status().isCreated())
			.andDo(
				document(
					"createMatch", PayloadDocumentation.responseFields(
						PayloadDocumentation.fieldWithPath("id").description("The identifier (a String) for the created match."),
						PayloadDocumentation.fieldWithPath("whitePlayerId").description("The identifier for the white player of the created match."),
						PayloadDocumentation.fieldWithPath("blackPlayerId").description("The identifier for the black player of the created match."),
						PayloadDocumentation.fieldWithPath("movements").description("A list of the movements that have been made during this match."),
						PayloadDocumentation.subsectionWithPath("_links").description("Links related to this match.")
					)
				)
			)
			.andReturn()
			.getResponse().getContentAsString();

		ObjectMapper objectMapper = new ObjectMapper(); 
        JsonNode rootNode = objectMapper.readTree(responseBody);
		testMatchId = rootNode.get("id").asString();
	}
}

