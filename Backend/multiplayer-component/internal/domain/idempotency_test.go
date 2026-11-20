package domain

import "testing"

func TestCreationKeyIsScopedToUser(t *testing.T) {
	first := CreationKey("user-a", "request-1")
	if first != CreationKey("user-a", "request-1") {
		t.Fatal("same user and key should produce the same creation key")
	}
	if first == CreationKey("user-b", "request-1") {
		t.Fatal("different users must not share a creation key")
	}
}

func TestRequestFingerprintUsesCanonicalDefaults(t *testing.T) {
	request := CanonicalCreateRequest{
		CreatorColor: "white",
		TimeControl:  TimeControl{Minutes: 10},
		Visibility:   "private",
	}
	first, err := RequestFingerprint(request)
	if err != nil {
		t.Fatal(err)
	}
	second, err := RequestFingerprint(request)
	if err != nil {
		t.Fatal(err)
	}
	if first != second {
		t.Fatal("canonical fingerprint should be stable")
	}
	request.Visibility = "shared"
	third, err := RequestFingerprint(request)
	if err != nil {
		t.Fatal(err)
	}
	if first == third {
		t.Fatal("different requests must have different fingerprints")
	}
}

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
