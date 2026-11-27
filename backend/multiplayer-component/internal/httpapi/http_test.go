package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"insightfulgames/multiplayer-component/internal/gamelogic"
	"insightfulgames/multiplayer-component/internal/realtime"
	"insightfulgames/multiplayer-component/internal/service"

	"github.com/gorilla/websocket"
)

func TestHealthEndpointAndUnknownRoute(t *testing.T) {
	handler := New(nil, realtime.NewHub(), nil, slog.New(slog.NewTextHandler(io.Discard, nil)))

	health := httptest.NewRecorder()
	handler.ServeHTTP(health, httptest.NewRequest(http.MethodGet, "/health", nil))
	if health.Code != http.StatusOK || health.Body.String() != "{\"status\":\"ok\"}\n" {
		t.Fatalf("health response = %d %q", health.Code, health.Body.String())
	}

	missing := httptest.NewRecorder()
	handler.ServeHTTP(missing, httptest.NewRequest(http.MethodGet, "/missing", nil))
	if missing.Code != http.StatusNotFound || missing.Header().Get("Content-Type") != "application/json" {
		t.Fatalf("unknown route response = %d %q", missing.Code, missing.Body.String())
	}
}

func TestWritePumpSendsGameOverBeforeClosingSocket(t *testing.T) {
	api := &API{}
	upgrader := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		client := realtime.NewClient("user", conn)
		go api.writePump(client)
		client.Send <- []byte(`{"type":"state","state":{}}`)
		client.Send <- []byte(`{"type":"game_over","result":"1-0","endReason":"resignation"}`)
	}))
	defer server.Close()

	conn, _, err := websocket.DefaultDialer.Dial("ws"+strings.TrimPrefix(server.URL, "http"), nil)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	if err := conn.SetReadDeadline(time.Now().Add(2 * time.Second)); err != nil {
		t.Fatal(err)
	}

	for _, expectedType := range []string{"state", "game_over"} {
		_, payload, err := conn.ReadMessage()
		if err != nil {
			t.Fatalf("read %s: %v", expectedType, err)
		}
		var message struct {
			Type string `json:"type"`
		}
		if err := json.Unmarshal(payload, &message); err != nil || message.Type != expectedType {
			t.Fatalf("message = %s, want type %q", payload, expectedType)
		}
	}
	_, _, err = conn.ReadMessage()
	closeError, ok := err.(*websocket.CloseError)
	if !ok || closeError.Code != websocket.CloseNormalClosure {
		t.Fatalf("socket close = %v, want normal close after game_over", err)
	}
}

func TestSocketCloseCodeDistinguishesAuthorizationFromServiceFailure(t *testing.T) {
	tests := []struct {
		name string
		err  error
		code int
	}{
		{name: "unauthorized", err: &service.ServiceError{Code: "UNAUTHORIZED"}, code: 4401},
		{name: "missing match", err: &service.ServiceError{Code: "MATCH_NOT_FOUND"}, code: 4404},
		{name: "dependency failure", err: &service.ServiceError{Code: "SERVICES_UNAVAILABLE"}, code: websocket.CloseInternalServerErr},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			code, _ := socketCloseForError(test.err)
			if code != test.code {
				t.Fatalf("close code = %d, want %d", code, test.code)
			}
		})
	}
}

// stubLogic es un Game Logic que falla si se le llama: el hub no debe consultarlo al recibir un publish.
type stubLogic struct{ called bool }

func (l *stubLogic) fail() (gamelogic.Response, error) {
	l.called = true
	return gamelogic.Response{}, errors.New("Game Logic must not be called")
}

func (l *stubLogic) Get(context.Context, string) (gamelogic.Response, error)        { return l.fail() }
func (l *stubLogic) GetByMatch(context.Context, string) (gamelogic.Response, error) { return l.fail() }
func (l *stubLogic) Move(context.Context, string, string, int64) (gamelogic.Response, error) {
	return l.fail()
}
func (l *stubLogic) Resign(context.Context, string, string) (gamelogic.Response, error) {
	return l.fail()
}
func (l *stubLogic) Abandon(context.Context, string, string) (gamelogic.Response, error) {
	return l.fail()
}
func (l *stubLogic) Draw(context.Context, string, string, string) (gamelogic.Response, error) {
	return l.fail()
}

const (
	publishMatchID = "22222222-2222-4222-8222-222222222222"
	publishGameID  = "11111111-1111-4111-8111-111111111111"
)

func publishState(version int, status string) string {
	return `{"gameId":"` + publishGameID + `","matchId":"` + publishMatchID + `","mode":"multiplayer",` +
		`"status":"` + status + `","turn":"white","version":` + string(rune('0'+version)) + `,"visibility":"private",` +
		`"participants":[],"moves":[{"uci":"e2e4"}],"result":null,"endReason":null}`
}

func newPublishAPI(logic *stubLogic) (http.Handler, *realtime.Hub) {
	hub := realtime.NewHub()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	app := service.New(logic, hub, time.Second, logger)
	return New(app, hub, nil, logger), hub
}

func postPublish(handler http.Handler, matchID, body string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodPost, "/internal/multiplayer/matches/"+matchID+"/publish", strings.NewReader(body))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func TestPublishRouteBroadcastsTheStateWithoutCallingGameLogic(t *testing.T) {
	logic := &stubLogic{}
	handler, hub := newPublishAPI(logic)
	client := realtime.NewClient("user", nil)
	hub.Add(publishMatchID, client)

	response := postPublish(handler, publishMatchID, `{"state":`+publishState(2, "in_progress")+`}`)

	if response.Code != http.StatusNoContent || response.Body.Len() != 0 {
		t.Fatalf("publish response = %d %q, want an empty 204", response.Code, response.Body.String())
	}
	var message struct {
		Type     string `json:"type"`
		LastMove string `json:"lastMove"`
	}
	select {
	case payload := <-client.Send:
		if err := json.Unmarshal(payload, &message); err != nil {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		t.Fatal("the connected client did not receive the published state")
	}
	if message.Type != "state" || message.LastMove != "e2e4" {
		t.Fatalf("message = %+v, want state with lastMove e2e4", message)
	}
	if logic.called {
		t.Fatal("publish called Game Logic")
	}
}

func TestPublishRouteSendsGameOverAfterTheFinalState(t *testing.T) {
	handler, hub := newPublishAPI(&stubLogic{})
	client := realtime.NewClient("user", nil)
	hub.Add(publishMatchID, client)

	postPublish(handler, publishMatchID, `{"state":`+publishState(3, "finished")+`}`)

	var types []string
	for range 2 {
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
			t.Fatalf("messages = %v, want state then game_over", types)
		}
	}
	if types[0] != "state" || types[1] != "game_over" {
		t.Fatalf("messages = %v, want state then game_over", types)
	}
}

func TestPublishRouteRejectsInvalidRequests(t *testing.T) {
	handler, _ := newPublishAPI(&stubLogic{})
	tests := []struct {
		name    string
		matchID string
		body    string
		status  int
		code    string
	}{
		{"invalid json", publishMatchID, `no es json`, http.StatusBadRequest, "VALIDATION_ERROR"},
		{"missing state", publishMatchID, `{}`, http.StatusBadRequest, "VALIDATION_ERROR"},
		{"state without ids", publishMatchID, `{"state":{"status":"waiting"}}`, http.StatusBadRequest, "VALIDATION_ERROR"},
		{"state of another match", "33333333-3333-4333-8333-333333333333", `{"state":` + publishState(1, "waiting") + `}`, http.StatusBadRequest, "VALIDATION_ERROR"},
		{"match id is not a uuid", "no-es-uuid", `{"state":` + publishState(1, "waiting") + `}`, http.StatusNotFound, "MATCH_NOT_FOUND"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			response := postPublish(handler, test.matchID, test.body)
			var envelope struct {
				Error struct {
					Code string `json:"code"`
				} `json:"error"`
			}
			if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
				t.Fatalf("body %q is not an error envelope: %v", response.Body.String(), err)
			}
			if response.Code != test.status || envelope.Error.Code != test.code {
				t.Fatalf("response = %d %s, want %d %s", response.Code, envelope.Error.Code, test.status, test.code)
			}
		})
	}
}

func TestRestRoutesMovedToTheGateway(t *testing.T) {
	handler, _ := newPublishAPI(&stubLogic{})
	routes := []struct{ method, path string }{
		{http.MethodPost, "/internal/multiplayer/matches"},
		{http.MethodPost, "/internal/multiplayer/matches/" + publishMatchID + "/join"},
		{http.MethodGet, "/internal/multiplayer/matches/" + publishMatchID},
		{http.MethodPost, "/internal/multiplayer/matches/" + publishMatchID + "/resign"},
		{http.MethodPatch, "/internal/multiplayer/matches/" + publishMatchID + "/visibility"},
		{http.MethodGet, "/internal/multiplayer/matches/" + publishMatchID + "/publish"},
	}
	for _, route := range routes {
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(route.method, route.path, strings.NewReader("{}")))
		if response.Code != http.StatusNotFound {
			t.Fatalf("%s %s = %d, want 404 (the gateway orchestrates this route)", route.method, route.path, response.Code)
		}
	}
}
