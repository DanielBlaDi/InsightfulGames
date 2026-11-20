package gamelogic

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestGetByMatchUsesInternalGatewayRoute(t *testing.T) {
	const matchID = "22222222-2222-4222-8222-222222222222"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/internal/logic/games/by-match/"+matchID {
			t.Errorf("request = %s %s", r.Method, r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"gameId":"33333333-3333-4333-8333-333333333333","matchId":"22222222-2222-4222-8222-222222222222","mode":"multiplayer","status":"waiting","createdAt":"2026-11-02T10:00:00Z"}`))
	}))
	defer server.Close()

	client := NewClient(server.URL, time.Second)
	response, err := client.GetByMatch(context.Background(), matchID)
	if err != nil {
		t.Fatal(err)
	}
	if response.State.MatchID != matchID || response.State.GameID == "" {
		t.Fatalf("unexpected GameState: %+v", response.State)
	}
}

func TestClientReturnsContractError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusConflict)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"error": map[string]string{"code": "GAME_NOT_WAITING", "message": "already joined"},
		})
	}))
	defer server.Close()

	client := NewClient(server.URL, time.Second)
	_, err := client.Join(context.Background(), "33333333-3333-4333-8333-333333333333", "22222222-2222-4222-8222-222222222222")
	apiError, ok := err.(*APIError)
	if !ok {
		t.Fatalf("error = %T %v, want *APIError", err, err)
	}
	if apiError.StatusCode != http.StatusConflict || apiError.Code != "GAME_NOT_WAITING" {
		t.Fatalf("API error = %+v", apiError)
	}
}
