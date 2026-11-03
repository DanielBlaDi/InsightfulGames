package httpapi

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

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
