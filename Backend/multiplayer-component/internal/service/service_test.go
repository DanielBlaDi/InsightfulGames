package service

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"sync"
	"testing"
	"time"

	"insightfulgames/multiplayer-component/internal/domain"
	"insightfulgames/multiplayer-component/internal/gamelogic"
	"insightfulgames/multiplayer-component/internal/realtime"
)

const (
	creatorID = "11111111-1111-4111-8111-111111111111"
	rivalID   = "22222222-2222-4222-8222-222222222222"
)

type fakeLogic struct {
	mu             sync.Mutex
	statesByGameID map[string]domain.GameState
	creationByKey  map[string]string
	lastPayload    map[string]any
	createStatus   int
	moveCalls      int
	callCount      int
}

func (f *fakeLogic) calls() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.callCount
}

func newFakeLogic() *fakeLogic {
	return &fakeLogic{
		statesByGameID: make(map[string]domain.GameState),
		creationByKey:  make(map[string]string),
		createStatus:   http.StatusCreated,
	}
}

func (f *fakeLogic) Create(_ context.Context, payload any) (gamelogic.Response, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.callCount++
	body, ok := payload.(map[string]any)
	if !ok {
		return gamelogic.Response{}, errors.New("unexpected create payload")
	}
	f.lastPayload = body
	creationKey := body["creationKey"].(string)
	fingerprint := body["requestFingerprint"].(string)
	if gameID, exists := f.creationByKey[creationKey]; exists {
		state := f.statesByGameID[gameID]
		if stateRawField(state.Raw, "requestFingerprint") != fingerprint {
			return gamelogic.Response{}, &gamelogic.APIError{StatusCode: http.StatusConflict, Code: "IDEMPOTENCY_KEY_REUSED", Message: "key reused"}
		}
		return gamelogic.Response{State: state, StatusCode: http.StatusOK}, nil
	}
	matchID := body["matchId"].(string)
	participantsJSON, _ := json.Marshal(body["participants"])
	var participants []domain.Participant
	_ = json.Unmarshal(participantsJSON, &participants)
	state := testState(matchID, "waiting", "white", 0, participants)
	raw, _ := json.Marshal(map[string]any{
		"gameId": state.GameID, "matchId": state.MatchID, "mode": "multiplayer",
		"status": state.Status, "turn": state.Turn, "version": state.Version,
		"visibility": body["visibility"], "participants": participants,
		"createdAt": "2026-11-02T10:00:00Z", "requestFingerprint": fingerprint,
	})
	state, _ = domain.DecodeGameState(raw)
	f.statesByGameID[state.GameID] = state
	f.creationByKey[creationKey] = state.GameID
	return gamelogic.Response{State: state, StatusCode: f.createStatus}, nil
}

func (f *fakeLogic) Join(_ context.Context, gameID, userID string) (gamelogic.Response, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.callCount++
	state := f.statesByGameID[gameID]
	if state.Status != "waiting" {
		return gamelogic.Response{}, &gamelogic.APIError{StatusCode: http.StatusConflict, Code: "GAME_NOT_WAITING", Message: "not waiting"}
	}
	color := "white"
	if state.Participants[0].Color == color {
		color = "black"
	}
	state.Participants = append(state.Participants, domain.Participant{UserID: userID, Color: color})
	state.Status, state.Turn, state.Version = "in_progress", "white", state.Version+1
	state = f.save(state, "")
	return gamelogic.Response{State: state, StatusCode: http.StatusOK}, nil
}

func (f *fakeLogic) Get(_ context.Context, gameID string) (gamelogic.Response, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.callCount++
	state, ok := f.statesByGameID[gameID]
	if !ok {
		return gamelogic.Response{}, &gamelogic.APIError{StatusCode: http.StatusNotFound, Code: "GAME_NOT_FOUND", Message: "missing"}
	}
	return gamelogic.Response{State: state, StatusCode: http.StatusOK}, nil
}

func (f *fakeLogic) GetByMatch(_ context.Context, matchID string) (gamelogic.Response, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.callCount++
	for _, state := range f.statesByGameID {
		if state.MatchID == matchID {
			return gamelogic.Response{State: state, StatusCode: http.StatusOK}, nil
		}
	}
	return gamelogic.Response{}, &gamelogic.APIError{StatusCode: http.StatusNotFound, Code: "GAME_NOT_FOUND", Message: "missing"}
}

func (f *fakeLogic) Move(_ context.Context, gameID, uci string, expectedVersion int64) (gamelogic.Response, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.callCount++
	state := f.statesByGameID[gameID]
	f.moveCalls++
	if state.Version != expectedVersion {
		return gamelogic.Response{}, &gamelogic.APIError{StatusCode: http.StatusConflict, Code: "VERSION_CONFLICT", Message: "stale"}
	}
	nextTurn := "black"
	if state.Turn == "black" {
		nextTurn = "white"
	}
	state.Turn = nextTurn
	state.Version++
	state.Moves = append(state.Moves, domain.Move{UCI: uci})
	state = f.save(state, "")
	return gamelogic.Response{State: state, StatusCode: http.StatusOK}, nil
}

func (f *fakeLogic) Resign(context.Context, string, string) (gamelogic.Response, error) {
	return gamelogic.Response{}, errors.New("not used")
}

func (f *fakeLogic) Abandon(_ context.Context, gameID, _ string) (gamelogic.Response, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.callCount++
	state := f.statesByGameID[gameID]
	if state.IsFinished() {
		return gamelogic.Response{}, &gamelogic.APIError{StatusCode: http.StatusUnprocessableEntity, Code: "GAME_FINISHED", Message: "already finished"}
	}
	state.Status = "finished"
	state.Result = stringPointer("0-1")
	state.EndReason = stringPointer("abandonment")
	state.Version++
	state = f.save(state, "")
	return gamelogic.Response{State: state, StatusCode: http.StatusOK}, nil
}

func (f *fakeLogic) Draw(context.Context, string, string, string) (gamelogic.Response, error) {
	return gamelogic.Response{}, errors.New("not used")
}

func (f *fakeLogic) SetVisibility(_ context.Context, gameID, visibility string, expectedVersion int64) (gamelogic.Response, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	state := f.statesByGameID[gameID]
	if state.Version != expectedVersion {
		return gamelogic.Response{}, &gamelogic.APIError{StatusCode: http.StatusConflict, Code: "VERSION_CONFLICT", Message: "stale"}
	}
	state.Visibility = visibility
	state.Version++
	state = f.save(state, "")
	return gamelogic.Response{State: state, StatusCode: http.StatusOK}, nil
}

func (f *fakeLogic) markFinished(matchID string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	for gameID, state := range f.statesByGameID {
		if state.MatchID == matchID {
			state.Status = "finished"
			state.Result = stringPointer("1-0")
			state.EndReason = stringPointer("resignation")
			state.Version++
			f.statesByGameID[gameID] = f.save(state, "")
			return
		}
	}
}

func (f *fakeLogic) save(state domain.GameState, createdAt string) domain.GameState {
	data := map[string]any{
		"gameId": state.GameID, "matchId": state.MatchID, "mode": "multiplayer",
		"status": state.Status, "turn": state.Turn, "version": state.Version,
		"visibility": state.Visibility, "participants": state.Participants,
		"moves": state.Moves, "result": state.Result, "endReason": state.EndReason,
		"drawOffer": state.DrawOffer,
	}
	if createdAt != "" {
		data["createdAt"] = createdAt
	}
	raw, _ := json.Marshal(data)
	state, _ = domain.DecodeGameState(raw)
	f.statesByGameID[state.GameID] = state
	return state
}

func testState(matchID, status, turn string, version int64, participants []domain.Participant) domain.GameState {
	raw, _ := json.Marshal(map[string]any{
		"gameId": "33333333-3333-4333-8333-333333333333", "matchId": matchID,
		"mode": "multiplayer", "status": status, "turn": turn, "version": version,
		"visibility": "private", "participants": participants, "moves": []domain.Move{},
	})
	state, _ := domain.DecodeGameState(raw)
	return state
}

func stateRawField(raw json.RawMessage, field string) string {
	var values map[string]json.RawMessage
	_ = json.Unmarshal(raw, &values)
	var value string
	_ = json.Unmarshal(values[field], &value)
	return value
}

func newTestService(logic *fakeLogic) *Service {
	app, _ := newTestServiceWithHub(logic)
	return app
}

func newTestServiceWithHub(logic *fakeLogic) (*Service, *realtime.Hub) {
	hub := realtime.NewHub()
	return New(logic, hub, time.Second, slog.New(slog.NewTextHandler(io.Discard, nil))), hub
}

func stringPointer(value string) *string {
	return &value
}

// createMatch hace lo que hace el gateway: crea la partida en Game Logic. El hub no sabe nada hasta que
// llega un publish o un cliente se conecta; seed simula ese primer contacto.
func createMatch(t *testing.T, logic *fakeLogic) domain.GameState {
	t.Helper()
	response, err := logic.Create(context.Background(), map[string]any{
		"mode": "multiplayer", "matchId": "55555555-5555-4555-8555-555555555555",
		"visibility":         "private",
		"participants":       []domain.Participant{{UserID: creatorID, Color: "white"}},
		"creationKey":        "k-" + t.Name(),
		"requestFingerprint": "fp",
	})
	if err != nil {
		t.Fatal(err)
	}
	return response.State
}

// joinMatch hace lo que hace el gateway al unirse: Game Logic une al rival.
func joinMatch(t *testing.T, logic *fakeLogic, state domain.GameState) domain.GameState {
	t.Helper()
	response, err := logic.Join(context.Background(), state.GameID, rivalID)
	if err != nil {
		t.Fatal(err)
	}
	return response.State
}

// publish es el aviso del gateway al hub.
func publish(t *testing.T, app *Service, state domain.GameState, gameOver *bool) {
	t.Helper()
	if err := app.ApplyPublish(state.MatchID, PublishRequest{State: state.Raw, GameOver: gameOver}); err != nil {
		t.Fatal(err)
	}
}

func readMessageTypes(t *testing.T, client *realtime.Client, count int) []string {
	t.Helper()
	var types []string
	for range count {
		select {
		case payload := <-client.Send:
			var message struct {
				Type string `json:"type"`
			}
			if err := json.Unmarshal(payload, &message); err != nil {
				t.Fatal(err)
			}
			types = append(types, message.Type)
		case <-time.After(time.Second):
			t.Fatalf("expected %d messages, got %v", count, types)
		}
	}
	return types
}

func assertNoMessage(t *testing.T, client *realtime.Client) {
	t.Helper()
	select {
	case payload := <-client.Send:
		t.Fatalf("unexpected message: %s", payload)
	case <-time.After(50 * time.Millisecond):
	}
}

func TestReconnectDeadlineStartsOnlyForAnActiveTurn(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, logic)
	publish(t, app, created, nil)

	app.Disconnected(created.MatchID, creatorID)
	session := app.getSession(created.MatchID)
	session.mu.Lock()
	waitingTimers := len(session.timers)
	session.mu.Unlock()
	if waitingTimers != 0 {
		t.Fatal("waiting invitation started a reconnect deadline")
	}

	joined := joinMatch(t, logic, created)
	publish(t, app, joined, nil) // el gateway avisa tras unir al rival
	moved, err := logic.Move(context.Background(), joined.GameID, "e2e4", joined.Version)
	if err != nil {
		t.Fatal(err)
	}
	publish(t, app, moved.State, nil) // y tras la jugada del creador, que pasa el turno al rival

	rivalClient := realtime.NewClient(rivalID, nil)
	hub.Add(created.MatchID, rivalClient)
	app.Disconnected(created.MatchID, creatorID)
	var notification struct {
		Type              string  `json:"type"`
		ReconnectDeadline *string `json:"reconnectDeadline"`
	}
	if err := json.Unmarshal(<-rivalClient.Send, &notification); err != nil {
		t.Fatal(err)
	}
	if notification.Type != "opponent_disconnected" || notification.ReconnectDeadline != nil {
		t.Fatalf("off-turn disconnect notification = %+v, want a null deadline", notification)
	}
	session.mu.Lock()
	offTurnTimers := len(session.timers)
	session.mu.Unlock()
	if offTurnTimers != 0 {
		t.Fatal("off-turn disconnect started a reconnect deadline")
	}

	hub.Remove(created.MatchID, rivalClient)
	app.Disconnected(created.MatchID, rivalID)
	session.mu.Lock()
	activeTurnTimers := len(session.timers)
	session.mu.Unlock()
	if activeTurnTimers != 1 {
		t.Fatal("active-turn disconnect did not start a reconnect deadline")
	}
	app.Connected(created.MatchID, rivalID)
	session.mu.Lock()
	canceledTimers := len(session.timers)
	session.mu.Unlock()
	if canceledTimers != 0 {
		t.Fatal("reconnection did not cancel its deadline")
	}
}

func TestSocketReconnectRefreshesFinishedStateAndCancelsDeadlines(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, logic)
	publish(t, app, joinMatch(t, logic, created), nil)
	rivalClient := realtime.NewClient(rivalID, nil)
	hub.Add(created.MatchID, rivalClient)

	app.Disconnected(created.MatchID, creatorID)
	<-rivalClient.Send
	logic.markFinished(created.MatchID)

	state, err := app.GetForSocket(context.Background(), created.MatchID, creatorID)
	if err != nil {
		t.Fatal(err)
	}
	if !state.IsFinished() {
		t.Fatal("reconnection did not return the finished GameState")
	}
	session := app.getSession(created.MatchID)
	session.mu.Lock()
	timerCount := len(session.timers)
	session.mu.Unlock()
	if timerCount != 0 {
		t.Fatal("finished match retained a reconnect deadline")
	}

	var messageTypes []string
	for range 2 {
		var message struct {
			Type string `json:"type"`
		}
		if err := json.Unmarshal(<-rivalClient.Send, &message); err != nil {
			t.Fatal(err)
		}
		messageTypes = append(messageTypes, message.Type)
	}
	if messageTypes[0] != "state" || messageTypes[1] != "game_over" {
		t.Fatalf("finished match messages = %v, want state followed by game_over", messageTypes)
	}
}

func TestReconnectDeadlineRefreshesGameFinishedAction(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, logic)
	publish(t, app, joinMatch(t, logic, created), nil)
	rivalClient := realtime.NewClient(rivalID, nil)
	hub.Add(created.MatchID, rivalClient)
	app.Disconnected(created.MatchID, creatorID)
	<-rivalClient.Send

	session := app.getSession(created.MatchID)
	session.mu.Lock()
	session.timers[creatorID].Stop()
	session.mu.Unlock()
	logic.markFinished(created.MatchID)
	app.expireReconnect(created.MatchID, creatorID)

	for _, expectedType := range []string{"state", "game_over"} {
		var message struct {
			Type string `json:"type"`
		}
		if err := json.Unmarshal(<-rivalClient.Send, &message); err != nil {
			t.Fatal(err)
		}
		if message.Type != expectedType {
			t.Fatalf("message type = %q, want %q", message.Type, expectedType)
		}
	}
}

func assertServiceError(t *testing.T, err error, status int, code string) {
	t.Helper()
	var serviceErr *ServiceError
	if !errors.As(err, &serviceErr) {
		t.Fatalf("error = %v, want ServiceError", err)
	}
	if serviceErr.StatusCode != status || serviceErr.Code != code {
		t.Fatalf("error = %d %s, want %d %s", serviceErr.StatusCode, serviceErr.Code, status, code)
	}
}

func TestPublishUpdatesTheSessionAndBroadcastsTheState(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, logic)
	creator := realtime.NewClient(creatorID, nil)
	hub.Add(created.MatchID, creator)

	joined := joinMatch(t, logic, created)
	publish(t, app, joined, nil)

	if types := readMessageTypes(t, creator, 1); types[0] != "state" {
		t.Fatalf("published message = %v, want state", types)
	}
	// La sesion ya conoce la partida en curso: un cierre del turno del rival empieza su plazo
	session := app.getSession(created.MatchID)
	session.mu.Lock()
	if !session.loaded || session.state.Status != "in_progress" || session.state.Version != joined.Version {
		t.Fatalf("session after publish = loaded %v, %+v", session.loaded, session.state)
	}
	session.mu.Unlock()
	hub.Remove(created.MatchID, creator)
	app.Disconnected(created.MatchID, creatorID)
	session.mu.Lock()
	defer session.mu.Unlock()
	if len(session.timers) != 1 {
		t.Fatal("the hub did not start the reconnect deadline from the published state")
	}
}

func TestPublishIncludesTheLastMoveWhenThereIsOne(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, logic)
	joined := joinMatch(t, logic, created)
	moved, err := logic.Move(context.Background(), joined.GameID, "e2e4", joined.Version)
	if err != nil {
		t.Fatal(err)
	}
	rival := realtime.NewClient(rivalID, nil)
	hub.Add(created.MatchID, rival)

	publish(t, app, moved.State, nil)

	var message struct {
		Type     string `json:"type"`
		LastMove string `json:"lastMove"`
	}
	if err := json.Unmarshal(<-rival.Send, &message); err != nil {
		t.Fatal(err)
	}
	if message.Type != "state" || message.LastMove != "e2e4" {
		t.Fatalf("message = %+v, want state with lastMove e2e4", message)
	}
}

func TestPublishOfAFinishedGameSendsStateThenGameOverAndCancelsDeadlines(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, logic)
	publish(t, app, joinMatch(t, logic, created), nil)
	rival := realtime.NewClient(rivalID, nil)
	hub.Add(created.MatchID, rival)
	app.Disconnected(created.MatchID, creatorID) // el rival (conectado) lo recibe y hay un plazo en marcha
	<-rival.Send

	logic.markFinished(created.MatchID)
	finished, _ := logic.Get(context.Background(), created.GameID)
	publish(t, app, finished.State, nil)

	if types := readMessageTypes(t, rival, 2); types[0] != "state" || types[1] != "game_over" {
		t.Fatalf("messages = %v, want state then game_over", types)
	}
	session := app.getSession(created.MatchID)
	session.mu.Lock()
	defer session.mu.Unlock()
	if len(session.timers) != 0 {
		t.Fatal("a finished game kept its reconnect deadline")
	}
}

func TestPublishCanSkipGameOver(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, logic)
	publish(t, app, joinMatch(t, logic, created), nil)
	client := realtime.NewClient(creatorID, nil)
	hub.Add(created.MatchID, client)
	logic.markFinished(created.MatchID)
	finished, _ := logic.Get(context.Background(), created.GameID)
	skip := false

	publish(t, app, finished.State, &skip)

	if types := readMessageTypes(t, client, 1); types[0] != "state" {
		t.Fatalf("messages = %v, want only state", types)
	}
	assertNoMessage(t, client)
}

func TestAStalePublishIsIgnoredAndTheSameVersionIsAccepted(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, logic)
	joined := joinMatch(t, logic, created)
	moved, _ := logic.Move(context.Background(), joined.GameID, "e2e4", joined.Version)
	client := realtime.NewClient(creatorID, nil)
	hub.Add(created.MatchID, client)

	publish(t, app, moved.State, nil)
	readMessageTypes(t, client, 1)
	publish(t, app, joined, nil) // version atrasada: no hace retroceder a la sesion ni a los clientes
	assertNoMessage(t, client)
	session := app.getSession(created.MatchID)
	session.mu.Lock()
	if session.state.Version != moved.State.Version || len(session.state.Moves) != 1 {
		t.Fatalf("session went back to version %d", session.state.Version)
	}
	session.mu.Unlock()

	publish(t, app, moved.State, nil) // la misma version (reenvio del estado vigente) si se entrega
	readMessageTypes(t, client, 1)
}

func TestPublishValidatesTheRequest(t *testing.T) {
	logic := newFakeLogic()
	app := newTestService(logic)
	created := createMatch(t, logic)
	otherMatch := "66666666-6666-4666-8666-666666666666"

	assertServiceError(t, app.ApplyPublish("no-es-uuid", PublishRequest{State: created.Raw}), http.StatusNotFound, "MATCH_NOT_FOUND")
	assertServiceError(t, app.ApplyPublish(created.MatchID, PublishRequest{}), http.StatusBadRequest, "VALIDATION_ERROR")
	assertServiceError(t, app.ApplyPublish(created.MatchID, PublishRequest{State: json.RawMessage(`{"nope":true}`)}), http.StatusBadRequest, "VALIDATION_ERROR")
	assertServiceError(t, app.ApplyPublish(created.MatchID, PublishRequest{State: json.RawMessage(`no es json`)}), http.StatusBadRequest, "VALIDATION_ERROR")
	assertServiceError(t, app.ApplyPublish(otherMatch, PublishRequest{State: created.Raw}), http.StatusBadRequest, "VALIDATION_ERROR")

	session := app.getSession(created.MatchID)
	session.mu.Lock()
	defer session.mu.Unlock()
	if session.loaded {
		t.Fatal("an invalid publish touched the session")
	}
}

func TestPublishNeverCallsGameLogic(t *testing.T) {
	logic := newFakeLogic()
	app := newTestService(logic)
	created := createMatch(t, logic)
	before := logic.calls()

	publish(t, app, joinMatch(t, logic, created), nil)

	if logic.calls() != before+1 { // solo la llamada de joinMatch; publish no consulta a nadie
		t.Fatalf("publish called Game Logic (%d calls, want %d)", logic.calls(), before+1)
	}
}

func TestTheHubOnlyAnswersPingAndIgnoresGameActions(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, logic)
	publish(t, app, joinMatch(t, logic, created), nil)
	client := realtime.NewClient(creatorID, nil)
	hub.Add(created.MatchID, client)
	before := logic.calls()

	app.HandleSocketMessage(context.Background(), created.MatchID, creatorID, []byte(`{"type":"ping"}`))
	if types := readMessageTypes(t, client, 1); types[0] != "pong" {
		t.Fatalf("answer to ping = %v, want pong", types)
	}

	for _, payload := range []string{
		`{"type":"move","uci":"e2e4","expectedVersion":1}`,
		`{"type":"resign"}`,
		`{"type":"draw_offer"}`,
		`{"type":"hacer_trampa"}`,
		`no es json`,
	} {
		app.HandleSocketMessage(context.Background(), created.MatchID, creatorID, []byte(payload))
	}
	assertNoMessage(t, client)
	if logic.calls() != before || logic.moveCalls != 0 {
		t.Fatal("the hub operated in Game Logic on a client message")
	}
}

func TestPublishSendsEventsAfterTheStateAndBeforeGameOver(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, logic)
	joined := joinMatch(t, logic, created)
	client := realtime.NewClient(rivalID, nil)
	hub.Add(created.MatchID, client)

	offered := map[string]any{"type": "draw_offered", "by": "white"}
	if err := app.ApplyPublish(created.MatchID, PublishRequest{State: joined.Raw, Events: []map[string]any{offered}}); err != nil {
		t.Fatal(err)
	}
	payloads := [][]byte{<-client.Send, <-client.Send}
	var event struct {
		Type string `json:"type"`
		By   string `json:"by"`
	}
	if err := json.Unmarshal(payloads[1], &event); err != nil {
		t.Fatal(err)
	}
	var first struct {
		Type string `json:"type"`
	}
	_ = json.Unmarshal(payloads[0], &first)
	if first.Type != "state" || event.Type != "draw_offered" || event.By != "white" {
		t.Fatalf("messages = %s then %s, want state then draw_offered by white", payloads[0], payloads[1])
	}

	// con la partida terminada: state, evento y game_over, en ese orden
	logic.markFinished(created.MatchID)
	finished, _ := logic.Get(context.Background(), created.GameID)
	declined := map[string]any{"type": "draw_declined"}
	if err := app.ApplyPublish(created.MatchID, PublishRequest{State: finished.State.Raw, Events: []map[string]any{declined}}); err != nil {
		t.Fatal(err)
	}
	types := readMessageTypes(t, client, 3)
	if types[0] != "state" || types[1] != "draw_declined" || types[2] != "game_over" {
		t.Fatalf("messages = %v, want state, draw_declined, game_over", types)
	}
}

func TestPublishRejectsUnsupportedEventsWithoutTouchingTheSession(t *testing.T) {
	logic := newFakeLogic()
	app := newTestService(logic)
	created := createMatch(t, logic)

	for _, event := range []map[string]any{{"type": "error", "code": "X"}, {"type": "opponent_connected"}, {"by": "white"}, {"type": 5}} {
		err := app.ApplyPublish(created.MatchID, PublishRequest{State: created.Raw, Events: []map[string]any{event}})
		assertServiceError(t, err, http.StatusBadRequest, "VALIDATION_ERROR")
	}
	session := app.getSession(created.MatchID)
	session.mu.Lock()
	defer session.mu.Unlock()
	if session.loaded {
		t.Fatal("an invalid publish touched the session")
	}
}
