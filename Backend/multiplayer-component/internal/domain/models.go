package domain

import (
	"encoding/json"
	"fmt"
	"regexp"
)

var uuidPattern = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

type TimeControl struct {
	Minutes int `json:"minutes"`
}

type CreateMatchRequest struct {
	TimeControl  *TimeControl `json:"timeControl,omitempty"`
	Visibility   string       `json:"visibility,omitempty"`
	CreatorColor string       `json:"creatorColor"`
}

type Participant struct {
	UserID string `json:"userId"`
	Color  string `json:"color"`
}

type GameState struct {
	GameID       string          `json:"gameId"`
	MatchID      string          `json:"matchId"`
	Mode         string          `json:"mode"`
	Status       string          `json:"status"`
	Turn         string          `json:"turn"`
	Version      int64           `json:"version"`
	Visibility   string          `json:"visibility"`
	Participants []Participant   `json:"participants"`
	DrawOffer    *string         `json:"drawOffer"`
	Result       *string         `json:"result"`
	EndReason    *string         `json:"endReason"`
	CreatedAt    string          `json:"createdAt"`
	Moves        []Move          `json:"moves"`
	Raw          json.RawMessage `json:"-"`
}

type Move struct {
	UCI string `json:"uci"`
}

func DecodeGameState(raw []byte) (GameState, error) {
	var state GameState
	if err := json.Unmarshal(raw, &state); err != nil {
		return GameState{}, fmt.Errorf("decode GameState: %w", err)
	}
	if state.GameID == "" || state.MatchID == "" {
		return GameState{}, fmt.Errorf("GameState is missing gameId or matchId")
	}
	state.Raw = append(json.RawMessage(nil), raw...)
	return state, nil
}

func IsUUID(value string) bool {
	return uuidPattern.MatchString(value)
}

func (s GameState) SideFor(userID string) (string, bool) {
	for _, participant := range s.Participants {
		if participant.UserID == userID {
			return participant.Color, true
		}
	}
	return "", false
}

func (s GameState) IsFinished() bool {
	return s.Status == "finished" || s.Result != nil
}

func (s GameState) IsPlayersTurn(userID string) bool {
	side, ok := s.SideFor(userID)
	return ok && side == s.Turn
}

func (s GameState) LastMove() string {
	if len(s.Moves) == 0 {
		return ""
	}
	return s.Moves[len(s.Moves)-1].UCI
}

type APIError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type ErrorEnvelope struct {
	Error APIError `json:"error"`
}
