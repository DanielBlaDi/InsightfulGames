package domain

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
)

type CanonicalCreateRequest struct {
	CreatorColor string      `json:"creatorColor"`
	TimeControl  TimeControl `json:"timeControl"`
	Visibility   string      `json:"visibility"`
}

func CreationKey(userID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(userID + "\n" + idempotencyKey))
	return hex.EncodeToString(sum[:])
}

func RequestFingerprint(request CanonicalCreateRequest) (string, error) {
	encoded, err := json.Marshal(request)
	if err != nil {
		return "", fmt.Errorf("encode canonical create request: %w", err)
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}
