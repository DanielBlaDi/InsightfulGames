package domain

import "testing"

func TestDecodeGameStatePreservesOriginalJSON(t *testing.T) {
	raw := []byte(`{"gameId":"11111111-1111-4111-8111-111111111111","matchId":"22222222-2222-4222-8222-222222222222","mode":"multiplayer","status":"waiting","participants":[],"extension":{"value":true}}`)
	state, err := DecodeGameState(raw)
	if err != nil {
		t.Fatal(err)
	}
	if string(state.Raw) != string(raw) {
		t.Fatalf("raw response changed: got %s", state.Raw)
	}
}

func TestDecodeGameStateRequiresGameAndMatchIDs(t *testing.T) {
	for _, raw := range []string{
		`{"matchId":"22222222-2222-4222-8222-222222222222"}`,
		`{"gameId":"11111111-1111-4111-8111-111111111111"}`,
		`no es json`,
	} {
		if _, err := DecodeGameState([]byte(raw)); err == nil {
			t.Fatalf("DecodeGameState(%q) succeeded, want an error", raw)
		}
	}
}
