package chess;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.springframework.data.mongodb.core.query.Criteria.where;
import static org.springframework.data.mongodb.core.query.Query.query;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import chess.matches.Match;
import chess.matches.MatchFinishedMessage;
import chess.matches.MatchRepository;
import chess.matches.MatchStore;
import chess.matches.RabbitPublisher;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * Game Logic completo contra un MongoDB real (MONGO_TEST_URL). RabbitMQ se sustituye por un
 * publicador simulado para comprobar qué eventos se publican y cuándo.
 *
 * <p>Ejemplo: MONGO_TEST_URL=mongodb://localhost:27017/game_logic_test ./gradlew test
 */
@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named = "MONGO_TEST_URL", matches = ".+")
class GameLogicMongoIntegrationTest{

    static final String ALICE = "aaaaaaaa-1111-4111-8111-111111111111";
    static final String BOB = "bbbbbbbb-2222-4222-8222-222222222222";
    static final String ANONYMOUS = "00000000-0000-0000-0000-000000000000";

    @DynamicPropertySource
    static void mongo(DynamicPropertyRegistry registry){
        registry.add("MONGO_URL", () -> System.getenv("MONGO_TEST_URL"));
        registry.add("WAITING_TIMEOUT_MINUTES", () -> "2");
    }

    @Autowired MockMvc mvc;
    @Autowired MongoTemplate mongo;
    @Autowired MatchRepository repository;
    @Autowired MatchStore store;
    @MockitoBean RabbitPublisher publisher;

    final ObjectMapper json = new ObjectMapper();

    @BeforeEach
    void clean(){
        mongo.remove(new org.springframework.data.mongodb.core.query.Query(), Match.class);
        clearInvocations(publisher);
    }

    // ------------------------------------------------------------ utilidades

    record Reply(int status, JsonNode body){
        String code(){
            return body.path("error").path("code").asString();
        }
    }

    Reply call(MockHttpServletRequestBuilder request) throws Exception{
        MvcResult result = mvc.perform(request).andReturn();
        String text = result.getResponse().getContentAsString();
        return new Reply(result.getResponse().getStatus(), text.isEmpty() ? json.createObjectNode() : json.readTree(text));
    }

    Reply send(String method, String path, String body) throws Exception{
        MockHttpServletRequestBuilder request = switch(method){
            case "POST" -> post(path);
            case "PATCH" -> patch(path);
            case "DELETE" -> delete(path);
            default -> get(path);
        };
        if(body != null){
            request = request.contentType(MediaType.APPLICATION_JSON).content(body);
        }
        return call(request);
    }

    Reply create(String body) throws Exception{
        return send("POST", "/internal/logic/games", body);
    }

    String createLocal(boolean withClock) throws Exception{
        Reply reply = create("{\"mode\":\"local\",\"visibility\":\"private\",\"timeControl\":" + (withClock ? "{\"minutes\":10}" : "null")
            + ",\"botLevel\":null,\"participants\":[{\"userId\":\"" + ALICE + "\",\"color\":\"white\"},{\"userId\":\"" + ALICE + "\",\"color\":\"black\"}]}");
        assertThat(reply.status()).isEqualTo(201);
        return reply.body().get("gameId").asString();
    }

    String multiplayerBody(String matchId, String key, String fingerprint){
        return "{\"mode\":\"multiplayer\",\"visibility\":\"private\",\"timeControl\":{\"minutes\":10},\"botLevel\":null,\"matchId\":\"" + matchId
            + "\",\"participants\":[{\"userId\":\"" + ALICE + "\",\"color\":\"white\"}],\"creationKey\":\"" + key + "\",\"requestFingerprint\":\"" + fingerprint + "\"}";
    }

    /** Multijugador con ALICE en blancas y BOB unido en negras. */
    String createJoinedMultiplayer() throws Exception{
        Reply created = create(multiplayerBody(UUID.randomUUID().toString(), "key-" + UUID.randomUUID(), "fp"));
        assertThat(created.status()).isEqualTo(201);
        String id = created.body().get("gameId").asString();
        Reply joined = send("POST", "/internal/logic/games/" + id + "/join", "{\"userId\":\"" + BOB + "\"}");
        assertThat(joined.status()).isEqualTo(200);
        return id;
    }

    Reply move(String id, String uci, int version) throws Exception{
        return send("POST", "/internal/logic/games/" + id + "/moves", "{\"uci\":\"" + uci + "\",\"expectedVersion\":" + version + "}");
    }

    Reply state(String id) throws Exception{
        return send("GET", "/internal/logic/games/" + id, null);
    }

    void setField(String id, String field, Object value){
        mongo.updateFirst(query(where("_id").is(id)), new Update().set(field, value), Match.class);
    }

    MatchFinishedMessage lastEvent(){
        ArgumentCaptor<MatchFinishedMessage> captor = ArgumentCaptor.forClass(MatchFinishedMessage.class);
        verify(publisher, atLeastOnce()).publishMatchFinishedMessage(captor.capture());
        return captor.getValue();
    }

    // ------------------------------------------------------------ 1-3: creación y consulta

    @Test
    void createsSinglePlayerGamesWithAndWithoutClock() throws Exception{
        Reply bot = create("{\"mode\":\"vs_bot\",\"visibility\":\"private\",\"timeControl\":null,\"botLevel\":5,\"participants\":[{\"userId\":\"" + ALICE + "\",\"color\":\"black\"}]}");
        assertThat(bot.status()).isEqualTo(201);
        assertThat(bot.body().get("status").asString()).isEqualTo("in_progress");
        assertThat(bot.body().get("clocks").isNull()).isTrue();
        assertThat(bot.body().get("version").asInt()).isZero();

        String timed = createLocal(true);
        JsonNode clocks = state(timed).body().get("clocks");
        assertThat(clocks.get("white").asInt()).isEqualTo(600000);
        assertThat(clocks.get("deadline").isNull()).isFalse();
        assertThat(clocks.has("timedOut")).as("isTimedOut() no forma parte del JSON").isFalse();
    }

    @Test
    void createsMultiplayerGamesIdempotently() throws Exception{
        String matchId = UUID.randomUUID().toString();
        Reply first = create(multiplayerBody(matchId, "key-1", "fp-1"));
        assertThat(first.status()).isEqualTo(201);
        assertThat(first.body().get("status").asString()).isEqualTo("waiting");
        assertThat(first.body().get("matchId").asString()).isEqualTo(matchId);
        assertThat(first.body().get("clocks").get("deadline").isNull()).as("el reloj empieza en join").isTrue();

        // Misma clave y mismo fingerprint: 200 con la misma partida (antes: 500 por requestFingerPrint)
        Reply again = create(multiplayerBody(matchId, "key-1", "fp-1"));
        assertThat(again.status()).isEqualTo(200);
        assertThat(again.body().get("gameId").asString()).isEqualTo(first.body().get("gameId").asString());

        Reply reused = create(multiplayerBody(UUID.randomUUID().toString(), "key-1", "otro"));
        assertThat(reused.status()).isEqualTo(409);
        assertThat(reused.code()).isEqualTo("IDEMPOTENCY_KEY_REUSED");

        Reply missingKey = create(multiplayerBody(UUID.randomUUID().toString(), "", "fp"));
        assertThat(missingKey.status()).isEqualTo(400);
        Reply badMinutes = create(multiplayerBody(UUID.randomUUID().toString(), "key-2", "fp").replace("\"minutes\":10", "\"minutes\":5"));
        assertThat(badMinutes.status()).isEqualTo(400);
        assertThat(repository.findAll()).hasSize(1);

        String gameId = first.body().get("gameId").asString();
        Reply byMatch = send("GET", "/internal/logic/games/by-match/" + matchId, null);
        assertThat(byMatch.body().get("gameId").asString()).isEqualTo(gameId);
        Reply missing = state(UUID.randomUUID().toString());
        assertThat(missing.status()).isEqualTo(404);
        assertThat(missing.code()).isEqualTo("GAME_NOT_FOUND");
    }

    @Test
    void joinStartsTheClockAndRejectsRepeatedJoins() throws Exception{
        String id = create(multiplayerBody(UUID.randomUUID().toString(), "key-j", "fp")).body().get("gameId").asString();
        Reply self = send("POST", "/internal/logic/games/" + id + "/join", "{\"userId\":\"" + ALICE + "\"}");
        assertThat(self.code()).isEqualTo("ALREADY_PARTICIPANT");
        Reply invalid = send("POST", "/internal/logic/games/" + id + "/join", "{\"userId\":null}");
        assertThat(invalid.status()).isEqualTo(400);

        Reply joined = send("POST", "/internal/logic/games/" + id + "/join", "{\"userId\":\"" + BOB + "\"}");
        assertThat(joined.body().get("status").asString()).isEqualTo("in_progress");
        assertThat(joined.body().get("participants").get(1).get("color").asString()).isEqualTo("black");
        assertThat(joined.body().get("clocks").get("deadline").isNull()).isFalse();
        assertThat(joined.body().get("version").asInt()).isEqualTo(1);

        Reply late = send("POST", "/internal/logic/games/" + id + "/join", "{\"userId\":\"" + UUID.randomUUID() + "\"}");
        assertThat(late.status()).isEqualTo(409);
        assertThat(late.code()).isEqualTo("GAME_NOT_WAITING");
    }

    // ------------------------------------------------------------ 4-10: jugadas

    @Test
    void movesWorkInGamesWithoutClock() throws Exception{
        // Causa del 500 reportado: getClocks() era null en partidas sin timeControl
        String id = createLocal(false);

        Reply first = move(id, "e2e4", 0);
        assertThat(first.status()).isEqualTo(200);
        assertThat(first.body().get("turn").asString()).isEqualTo("black");
        assertThat(first.body().get("version").asInt()).isEqualTo(1);
        assertThat(first.body().get("moves").get(0).get("color").asString()).isEqualTo("white");

        Reply second = move(id, "e7e5", 1);
        assertThat(second.status()).isEqualTo(200);
        assertThat(second.body().get("moves")).hasSize(2);
        assertThat(second.body().get("fen").asString()).startsWith("rnbqkbnr/pppp1ppp/8/4p3/4P3");

        Reply stored = state(id);
        assertThat(stored.body().get("version").asInt()).isEqualTo(2);
        assertThat(stored.body().get("clocks").isNull()).isTrue();
    }

    @Test
    void multiplayerMovesUpdateTheClocks() throws Exception{
        String id = createJoinedMultiplayer();

        Reply moved = move(id, "e2e4", 1);
        assertThat(moved.status()).isEqualTo(200);
        JsonNode clocks = moved.body().get("clocks");
        assertThat(clocks.get("white").asInt()).isLessThanOrEqualTo(600000);
        assertThat(clocks.get("black").asInt()).isEqualTo(600000);
        assertThat(Instant.parse(clocks.get("deadline").asString())).isAfter(Instant.now());
        assertThat(move(id, "e7e5", 2).status()).isEqualTo(200);
    }

    @Test
    void rejectsIllegalAndOutOfTurnMovesAndBadBodies() throws Exception{
        String id = createLocal(false);

        Reply illegal = move(id, "e2e5", 0);
        assertThat(illegal.status()).isEqualTo(422);
        assertThat(illegal.code()).isEqualTo("INVALID_MOVE");

        // Fuera de turno: negras intentan mover primero. Para Game Logic es una jugada ilegal en la posición.
        Reply outOfTurn = move(id, "e7e5", 0);
        assertThat(outOfTurn.status()).isEqualTo(422);
        assertThat(outOfTurn.code()).isEqualTo("INVALID_MOVE");

        Reply noVersion = send("POST", "/internal/logic/games/" + id + "/moves", "{\"uci\":\"e2e4\"}");
        assertThat(noVersion.status()).isEqualTo(400);
        assertThat(noVersion.code()).isEqualTo("VALIDATION_ERROR");

        assertThat(state(id).body().get("version").asInt()).as("ningún rechazo cambia la partida").isZero();
    }

    @Test
    void checkmateFinishesSavesAndThenPublishes() throws Exception{
        String id = createJoinedMultiplayer();
        int version = 1;
        for(String uci : new String[]{"f2f3", "e7e5", "g2g4"}){
            assertThat(move(id, uci, version++).status()).isEqualTo(200);
        }
        verify(publisher, never()).publishMatchFinishedMessage(any());

        Reply mate = move(id, "d8h4", version);
        assertThat(mate.status()).isEqualTo(200);
        assertThat(mate.body().get("status").asString()).isEqualTo("finished");
        assertThat(mate.body().get("result").asString()).isEqualTo("black");
        assertThat(mate.body().get("endReason").asString()).isEqualTo("checkmate");
        assertThat(mate.body().get("legalMoves").isEmpty()).isTrue();

        MatchFinishedMessage event = lastEvent();
        assertThat(event.eventId()).matches("[0-9a-f-]{36}");
        assertThat(event.gameId()).isEqualTo(id);
        assertThat(event.mode()).isEqualTo("multiplayer");
        assertThat(repository.findByGameId(id).orElseThrow().isFinished()).as("guardado antes de publicar").isTrue();

        Reply afterEnd = move(id, "e2e4", version + 1);
        assertThat(afterEnd.status()).isEqualTo(422);
        assertThat(afterEnd.code()).isEqualTo("GAME_FINISHED");
    }

    @Test
    void movesOnWaitingGamesAreNotInProgress() throws Exception{
        String id = create(multiplayerBody(UUID.randomUUID().toString(), "key-w", "fp")).body().get("gameId").asString();
        Reply reply = move(id, "e2e4", 0);
        assertThat(reply.status()).isEqualTo(409);
        assertThat(reply.code()).isEqualTo("GAME_NOT_IN_PROGRESS");
    }

    // ------------------------------------------------------------ 11-14: reloj, espera, timeout, expire

    @Test
    void expiredClockFinishesTheGameOnMoveAndOnTimeout() throws Exception{
        String onMove = createJoinedMultiplayer();
        setField(onMove, "clocks.deadline", Instant.now().minusSeconds(1).toString());

        Reply late = move(onMove, "e2e4", 1);
        assertThat(late.status()).isEqualTo(422);
        assertThat(late.code()).isEqualTo("CLOCK_EXPIRED");
        Reply closed = state(onMove);
        assertThat(closed.body().get("endReason").asString()).isEqualTo("timeout");
        assertThat(closed.body().get("result").asString()).isEqualTo("black");
        assertThat(closed.body().get("moves")).as("la jugada no se guarda").isEmpty();

        String timed = createJoinedMultiplayer();
        Reply notYet = send("POST", "/internal/logic/games/" + timed + "/timeout", "{\"expectedVersion\":1}");
        assertThat(notYet.code()).isEqualTo("CLOCK_NOT_EXPIRED");

        setField(timed, "clocks.deadline", Instant.now().minusSeconds(1).toString());
        Reply listed = send("GET", "/internal/logic/games/expired?limit=10", null);
        assertThat(listed.body().toString()).contains(timed).contains("\"reason\":\"clock\"");

        Reply stale = send("POST", "/internal/logic/games/" + timed + "/timeout", "{\"expectedVersion\":0}");
        assertThat(stale.status()).isEqualTo(409);
        assertThat(stale.code()).isEqualTo("VERSION_CONFLICT");

        Reply timeout = send("POST", "/internal/logic/games/" + timed + "/timeout", "{\"expectedVersion\":1}");
        assertThat(timeout.status()).isEqualTo(200);
        assertThat(timeout.body().get("status").asString()).isEqualTo("finished");
        assertThat(timeout.body().get("result").asString()).isEqualTo("black");
        assertThat(timeout.body().get("endReason").asString()).isEqualTo("timeout");
        assertThat(lastEvent().endReason()).isEqualTo("timeout");

        Reply again = send("POST", "/internal/logic/games/" + timed + "/timeout", "{\"expectedVersion\":2}");
        assertThat(again.status()).isEqualTo(422);
        assertThat(again.code()).isEqualTo("GAME_FINISHED");
    }

    @Test
    void timeoutOnAGameWithoutClockIsClockNotExpired() throws Exception{
        String id = createLocal(false);
        Reply reply = send("POST", "/internal/logic/games/" + id + "/timeout", "{\"expectedVersion\":0}");
        assertThat(reply.status()).as("antes: 500 por getClocks() null").isEqualTo(422);
        assertThat(reply.code()).isEqualTo("CLOCK_NOT_EXPIRED");
    }

    @Test
    void waitingGamesExpireAfterTheConfiguredTimeout() throws Exception{
        String id = create(multiplayerBody(UUID.randomUUID().toString(), "key-e", "fp")).body().get("gameId").asString();

        Reply early = send("POST", "/internal/logic/games/" + id + "/expire", "{\"expectedVersion\":0}");
        assertThat(early.status()).isEqualTo(422);
        assertThat(early.code()).isEqualTo("WAITING_NOT_EXPIRED");
        assertThat(send("GET", "/internal/logic/games/expired?limit=10", null).body()).isEmpty();

        setField(id, "createdAt", Instant.now().minusSeconds(121));
        Reply listed = send("GET", "/internal/logic/games/expired?limit=10", null);
        assertThat(listed.body()).hasSize(1);
        assertThat(listed.body().get(0).get("gameId").asString()).isEqualTo(id);
        assertThat(listed.body().get(0).get("version").asInt()).isZero();
        assertThat(listed.body().get(0).get("reason").asString()).isEqualTo("waiting");

        assertThat(send("POST", "/internal/logic/games/" + id + "/expire", "{\"expectedVersion\":3}").code()).isEqualTo("VERSION_CONFLICT");
        Reply expired = send("POST", "/internal/logic/games/" + id + "/expire", "{\"expectedVersion\":0}");
        assertThat(expired.status()).isEqualTo(200);
        assertThat(expired.body().get("endReason").asString()).isEqualTo("expired");
        assertThat(expired.body().get("result").isNull()).isTrue();
        assertThat(lastEvent().endReason()).isEqualTo("expired");

        assertThat(send("POST", "/internal/logic/games/" + id + "/expire", "{\"expectedVersion\":1}").code()).isEqualTo("GAME_FINISHED");
        String playing = createJoinedMultiplayer();
        assertThat(send("POST", "/internal/logic/games/" + playing + "/expire", "{\"expectedVersion\":1}").code()).isEqualTo("GAME_NOT_WAITING");
        assertThat(send("GET", "/internal/logic/games/expired", null).status()).isEqualTo(400);
    }

    // ------------------------------------------------------------ 15-16: versión y concurrencia

    @Test
    void staleVersionsAreRejectedWithVersionConflict() throws Exception{
        String id = createLocal(false);
        assertThat(move(id, "e2e4", 0).status()).isEqualTo(200);

        Reply stale = move(id, "e7e5", 0);
        assertThat(stale.status()).isEqualTo(409);
        assertThat(stale.code()).isEqualTo("VERSION_CONFLICT");

        Reply visibility = send("PATCH", "/internal/logic/games/" + id + "/visibility", "{\"visibility\":\"shared\",\"expectedVersion\":0}");
        assertThat(visibility.code()).isEqualTo("VERSION_CONFLICT");
        Reply invalid = send("PATCH", "/internal/logic/games/" + id + "/visibility", "{\"visibility\":\"public\",\"expectedVersion\":1}");
        assertThat(invalid.status()).isEqualTo(400);
        Reply ok = send("PATCH", "/internal/logic/games/" + id + "/visibility", "{\"visibility\":\"shared\",\"expectedVersion\":1}");
        assertThat(ok.body().get("visibility").asString()).isEqualTo("shared");
        assertThat(ok.body().get("version").asInt()).isEqualTo(2);
    }

    @Test
    void conditionalWriteLosesAgainstAConcurrentWriter(){
        Match game = new Match("local", null, "private", null, null, null, null,
            new ArrayList<>(List.of(new chess.matches.Participant(ALICE, "white"), new chess.matches.Participant(ALICE, "black"))));
        store.insert(game);

        Match firstReader = repository.findByGameId(game.getGameId()).orElseThrow();
        Match secondReader = repository.findByGameId(game.getGameId()).orElseThrow();
        firstReader.setVisibility("shared");
        firstReader.updateVersion();
        secondReader.setDrawOffer("white");
        secondReader.updateVersion();

        assertThat(store.replaceIfVersion(firstReader, 0)).isTrue();
        assertThat(store.replaceIfVersion(secondReader, 0)).as("la segunda escritura con la misma versión leída pierde").isFalse();
        Match stored = repository.findByGameId(game.getGameId()).orElseThrow();
        assertThat(stored.getVersion()).isEqualTo(1);
        assertThat(stored.getVisibility()).isEqualTo("shared");
        assertThat(stored.getDrawOffer()).isNull();
    }

    @Test
    void simultaneousMovesWithTheSameVersionApplyOnlyOne() throws Exception{
        for(int round = 0; round < 10; round++){
            String id = createJoinedMultiplayer();
            List<Reply> replies = race(
                () -> move(id, "e2e4", 1),
                () -> move(id, "d2d4", 1));

            assertThat(replies).extracting(Reply::status).containsExactlyInAnyOrder(200, 409);
            JsonNode stored = state(id).body();
            assertThat(stored.get("version").asInt()).isEqualTo(2);
            assertThat(stored.get("moves")).hasSize(1);
        }
    }

    @Test
    void simultaneousResignAndMoveLeaveAConsistentGame() throws Exception{
        for(int round = 0; round < 10; round++){
            String id = createJoinedMultiplayer();
            clearInvocations(publisher);
            List<Reply> replies = race(
                () -> move(id, "e2e4", 1),
                () -> send("POST", "/internal/logic/games/" + id + "/resign", "{\"side\":\"black\"}"));

            JsonNode stored = state(id).body();
            assertThat(stored.get("status").asString()).isEqualTo("finished");
            assertThat(stored.get("endReason").asString()).isEqualTo("surrender");
            assertThat(replies.get(1).status()).isEqualTo(200);
            // La jugada pudo entrar antes (version 3) o perder (version 2), nunca ambas a medias
            int moves = stored.get("moves").size();
            assertThat(stored.get("version").asInt()).isEqualTo(2 + moves);
            verify(publisher).publishMatchFinishedMessage(any());
        }
    }

    @SafeVarargs
    private List<Reply> race(Callable<Reply>... tasks) throws Exception{
        ExecutorService pool = Executors.newFixedThreadPool(tasks.length);
        CountDownLatch start = new CountDownLatch(1);
        try{
            List<Future<Reply>> futures = new ArrayList<>();
            for(Callable<Reply> task : tasks){
                futures.add(pool.submit(() -> {
                    start.await();
                    return task.call();
                }));
            }
            start.countDown();
            List<Reply> replies = new ArrayList<>();
            for(Future<Reply> future : futures){
                replies.add(future.get());
            }
            return replies;
        }finally{
            pool.shutdownNow();
        }
    }

    // ------------------------------------------------------------ otras rutas del contrato

    @Test
    void drawOfferStoresTheOffererAndOnlyTheRivalAccepts() throws Exception{
        String id = createJoinedMultiplayer();

        Reply offer = send("POST", "/internal/logic/games/" + id + "/draw/offer", "{\"side\":\"white\"}");
        assertThat(offer.body().get("drawOffer").asString()).isEqualTo("white");
        assertThat(send("POST", "/internal/logic/games/" + id + "/draw/offer", "{\"side\":\"black\"}").code()).isEqualTo("DRAW_ALREADY_OFFERED");
        assertThat(send("POST", "/internal/logic/games/" + id + "/draw/accept", "{\"side\":\"white\"}").code()).isEqualTo("DRAW_NOT_ALLOWED");
        assertThat(send("POST", "/internal/logic/games/" + id + "/draw/cancel", "{\"side\":\"black\"}").code()).isEqualTo("DRAW_NOT_ALLOWED");

        Reply accepted = send("POST", "/internal/logic/games/" + id + "/draw/accept", "{\"side\":\"black\"}");
        assertThat(accepted.status()).isEqualTo(200);
        assertThat(accepted.body().get("result").asString()).isEqualTo("draw");
        assertThat(accepted.body().get("endReason").asString()).isEqualTo("draw");
        assertThat(accepted.body().get("drawOffer").isNull()).isTrue();
        assertThat(lastEvent().endReason()).isEqualTo("draw");
    }

    @Test
    void resignRequiresAParticipantColor() throws Exception{
        Reply bot = create("{\"mode\":\"vs_bot\",\"visibility\":\"private\",\"timeControl\":null,\"botLevel\":5,\"participants\":[{\"userId\":\"" + ALICE + "\",\"color\":\"white\"}]}");
        String id = bot.body().get("gameId").asString();
        assertThat(send("POST", "/internal/logic/games/" + id + "/resign", "{\"side\":\"black\"}").status()).isEqualTo(400);
        Reply resigned = send("POST", "/internal/logic/games/" + id + "/resign", "{\"side\":\"white\"}");
        assertThat(resigned.body().get("result").asString()).isEqualTo("black");
        assertThat(resigned.body().get("endReason").asString()).isEqualTo("surrender");
    }

    @Test
    void historyAndAnalysisInputFollowTheContract() throws Exception{
        String id = createJoinedMultiplayer();
        send("POST", "/internal/logic/games/" + id + "/resign", "{\"side\":\"white\"}");
        createLocal(false);

        JsonNode page = send("GET", "/internal/logic/games?userId=" + BOB, null).body();
        JsonNode item = page.get("items").get(0);
        assertThat(item.get("color").asString()).isEqualTo("black");
        assertThat(item.get("endReason").asString()).isEqualTo("surrender");
        assertThat(item.has("matchId")).isTrue();
        JsonNode alice = send("GET", "/internal/logic/games?userId=" + ALICE, null).body().get("items");
        assertThat(alice.get(0).get("mode").asString()).isEqualTo("local");
        assertThat(alice.get(0).get("color").isNull()).isTrue();

        JsonNode analysis = send("GET", "/internal/logic/games/" + id + "/analysis-input", null).body();
        assertThat(analysis.get("status").asString()).isEqualTo("finished");
        assertThat(analysis.get("result").asString()).as("antes devolvía status en result").isEqualTo("black");
    }

    @Test
    void accountDeletionClosesAnonymizesOnceAndIsRepeatable() throws Exception{
        String multiplayer = createJoinedMultiplayer();
        String local = createLocal(false);
        String finished = createLocal(false);
        send("POST", "/internal/logic/games/" + finished + "/resign", "{\"side\":\"white\"}");
        clearInvocations(publisher);

        assertThat(send("DELETE", "/internal/logic/users/" + ALICE, null).status()).isEqualTo(204);

        JsonNode mp = state(multiplayer).body();
        assertThat(mp.get("endReason").asString()).isEqualTo("abandonment");
        assertThat(mp.get("result").asString()).as("gana el rival de quien se borró").isEqualTo("black");
        assertThat(mp.get("participants").get(0).get("userId").asString()).isEqualTo(ANONYMOUS);
        assertThat(mp.get("participants").get(0).get("color").asString()).isEqualTo("white");
        assertThat(mp.get("version").asInt()).isEqualTo(2);

        JsonNode lc = state(local).body();
        assertThat(lc.get("endReason").asString()).isEqualTo("account_deleted");
        assertThat(lc.get("result").isNull()).isTrue();
        assertThat(lc.get("participants").get(1).get("userId").asString()).isEqualTo(ANONYMOUS);

        JsonNode fn = state(finished).body();
        assertThat(fn.get("endReason").asString()).as("ya terminada: conserva su resultado").isEqualTo("surrender");
        // Se publican solo los dos cierres nuevos, no la partida ya terminada
        verify(publisher, org.mockito.Mockito.times(2)).publishMatchFinishedMessage(any());

        clearInvocations(publisher);
        assertThat(send("DELETE", "/internal/logic/users/" + ALICE, null).status()).isEqualTo(204);
        assertThat(state(multiplayer).body().get("version").asInt()).as("un reintento de la saga no cambia nada").isEqualTo(2);
        verify(publisher, never()).publishMatchFinishedMessage(any());
    }

    @Test
    void unknownRoutesAndBadParametersUseTheErrorShape() throws Exception{
        Reply unknown = send("GET", "/internal/logic/nope", null);
        assertThat(unknown.status()).isEqualTo(404);
        assertThat(unknown.code()).isEqualTo("NOT_FOUND");
        Reply badLimit = send("GET", "/internal/logic/games/expired?limit=abc", null);
        assertThat(badLimit.status()).isEqualTo(400);
        assertThat(badLimit.code()).isEqualTo("VALIDATION_ERROR");
    }
}
