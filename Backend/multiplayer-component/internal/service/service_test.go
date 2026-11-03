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
	state, ok := f.statesByGameID[gameID]
	if !ok {
		return gamelogic.Response{}, &gamelogic.APIError{StatusCode: http.StatusNotFound, Code: "GAME_NOT_FOUND", Message: "missing"}
	}
	return gamelogic.Response{State: state, StatusCode: http.StatusOK}, nil
}

func (f *fakeLogic) GetByMatch(_ context.Context, matchID string) (gamelogic.Response, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
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

func createMatch(t *testing.T, app *Service, key string) CreateResult {
	t.Helper()
	result, err := app.Create(context.Background(), creatorID, key, domain.CreateMatchRequest{CreatorColor: "white"})
	if err != nil {
		t.Fatal(err)
	}
	return result
}

func TestCreateUsesDefaultsAndDelegatesIdempotencyToGameLogic(t *testing.T) {
	logic := newFakeLogic()
	app := newTestService(logic)
	first := createMatch(t, app, "create-1")
	second := createMatch(t, app, "create-1")

	if first.MatchID != second.MatchID || second.Status != "waiting" || !second.Replayed {
		t.Fatalf("replayed create did not return original invitation: first=%+v second=%+v", first, second)
	}
	if logic.lastPayload["mode"] != "multiplayer" ||
		logic.lastPayload["visibility"] != "private" ||
		logic.lastPayload["creationKey"] == "" ||
		logic.lastPayload["requestFingerprint"] == "" {
		t.Fatalf("create payload is missing contract fields: %#v", logic.lastPayload)
	}
	timeControl := logic.lastPayload["timeControl"].(*domain.TimeControl)
	if timeControl.Minutes != 10 {
		t.Fatalf("default time control = %d, want 10", timeControl.Minutes)
	}
}

func TestCreateRejectsMissingKeyAndReusedKeyWithDifferentRequest(t *testing.T) {
	logic := newFakeLogic()
	app := newTestService(logic)
	_, err := app.Create(context.Background(), creatorID, "", domain.CreateMatchRequest{CreatorColor: "white"})
	assertServiceError(t, err, http.StatusBadRequest, "VALIDATION_ERROR")

	createMatch(t, app, "same-key")
	_, err = app.Create(context.Background(), creatorID, "same-key", domain.CreateMatchRequest{
		CreatorColor: "black",
	})
	assertServiceError(t, err, http.StatusConflict, "IDEMPOTENCY_KEY_REUSED")
}

func TestJoinAndPrivateMatchAuthorization(t *testing.T) {
	logic := newFakeLogic()
	app := newTestService(logic)
	created := createMatch(t, app, "join-1")

	joined, err := app.Join(context.Background(), created.MatchID, rivalID)
	if err != nil {
		t.Fatal(err)
	}
	if joined.Status != "in_progress" || len(joined.Participants) != 2 {
		t.Fatalf("joined state = %+v", joined)
	}
	_, err = app.Get(context.Background(), created.MatchID, "44444444-4444-4444-8444-444444444444")
	assertServiceError(t, err, http.StatusNotFound, "MATCH_NOT_FOUND")
}

func TestSocketMoveValidatesTurnAndVersionBeforeCallingGameLogic(t *testing.T) {
	logic := newFakeLogic()
	app := newTestService(logic)
	created := createMatch(t, app, "move-1")
	joined, err := app.Join(context.Background(), created.MatchID, rivalID)
	if err != nil {
		t.Fatal(err)
	}

	wrongTurn := []byte(`{"type":"move","uci":"e7e5","expectedVersion":1}`)
	app.HandleSocketMessage(context.Background(), created.MatchID, rivalID, wrongTurn)
	if logic.moveCalls != 0 {
		t.Fatal("wrong-turn move reached Game Logic")
	}

	move := []byte(`{"type":"move","uci":"e2e4","expectedVersion":1}`)
	app.HandleSocketMessage(context.Background(), created.MatchID, creatorID, move)
	if logic.moveCalls != 1 {
		t.Fatal("valid move was not sent to Game Logic")
	}
	state, err := app.GetForSocket(context.Background(), created.MatchID, rivalID)
	if err != nil {
		t.Fatal(err)
	}
	if state.Turn != "black" || state.Version != joined.Version+1 {
		t.Fatalf("state after move = turn %s version %d", state.Turn, state.Version)
	}
}

func TestReconnectDeadlineStartsOnlyForAnActiveTurn(t *testing.T) {
	logic := newFakeLogic()
	app, hub := newTestServiceWithHub(logic)
	created := createMatch(t, app, "reconnect-1")

	app.Disconnected(created.MatchID, creatorID)
	session := app.getSession(created.MatchID)
	session.mu.Lock()
	waitingTimers := len(session.timers)
	session.mu.Unlock()
	if waitingTimers != 0 {
		t.Fatal("waiting invitation started a reconnect deadline")
	}

	if _, err := app.Join(context.Background(), created.MatchID, rivalID); err != nil {
		t.Fatal(err)
	}
	move := []byte(`{"type":"move","uci":"e2e4","expectedVersion":1}`)
	app.HandleSocketMessage(context.Background(), created.MatchID, creatorID, move)

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
	created := createMatch(t, app, "reconnect-finished")
	if _, err := app.Join(context.Background(), created.MatchID, rivalID); err != nil {
		t.Fatal(err)
	}
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
	created := createMatch(t, app, "reconnect-action-finished")
	if _, err := app.Join(context.Background(), created.MatchID, rivalID); err != nil {
		t.Fatal(err)
	}
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
