package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"

	"insightfulgames/multiplayer-component/internal/domain"
	"insightfulgames/multiplayer-component/internal/gamelogic"
	"insightfulgames/multiplayer-component/internal/realtime"
)

var idempotencyKeyPattern = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,128}$`)

type Logic interface {
	Create(context.Context, any) (gamelogic.Response, error)
	Join(context.Context, string, string) (gamelogic.Response, error)
	Get(context.Context, string) (gamelogic.Response, error)
	GetByMatch(context.Context, string) (gamelogic.Response, error)
	Move(context.Context, string, string, int64) (gamelogic.Response, error)
	Resign(context.Context, string, string) (gamelogic.Response, error)
	Abandon(context.Context, string, string) (gamelogic.Response, error)
	Draw(context.Context, string, string, string) (gamelogic.Response, error)
	SetVisibility(context.Context, string, string, int64) (gamelogic.Response, error)
}

type Service struct {
	logic           Logic
	hub             *realtime.Hub
	reconnectWindow time.Duration
	logger          *slog.Logger
	mu              sync.Mutex
	sessions        map[string]*matchSession
	matchToGame     map[string]string
	processedEvent  map[string]struct{}
}

type matchSession struct {
	mu        sync.Mutex
	state     domain.GameState
	loaded    bool
	timers    map[string]*time.Timer
	deadlines map[string]time.Time
}

type CreateResult struct {
	MatchID   string
	Status    string
	CreatedAt string
	Replayed  bool
}

type ServiceError struct {
	StatusCode int
	Code       string
	Message    string
}

func (e *ServiceError) Error() string {
	return e.Code + ": " + e.Message
}

func New(logic Logic, hub *realtime.Hub, reconnectWindow time.Duration, logger *slog.Logger) *Service {
	return &Service{
		logic:           logic,
		hub:             hub,
		reconnectWindow: reconnectWindow,
		logger:          logger,
		sessions:        make(map[string]*matchSession),
		matchToGame:     make(map[string]string),
		processedEvent:  make(map[string]struct{}),
	}
}

func (s *Service) Create(ctx context.Context, userID, idempotencyKey string, request domain.CreateMatchRequest) (CreateResult, error) {
	if !domain.IsUUID(userID) {
		return CreateResult{}, serviceError(http.StatusUnauthorized, "UNAUTHORIZED", "A valid X-User-Id is required")
	}
	if !idempotencyKeyPattern.MatchString(idempotencyKey) {
		return CreateResult{}, serviceError(http.StatusBadRequest, "VALIDATION_ERROR", "Idempotency-Key must contain 1 to 128 valid characters")
	}
	if request.CreatorColor != "white" && request.CreatorColor != "black" {
		return CreateResult{}, serviceError(http.StatusBadRequest, "VALIDATION_ERROR", "creatorColor must be white or black")
	}
	if request.Visibility == "" {
		request.Visibility = "private"
	}
	if request.Visibility != "private" && request.Visibility != "shared" {
		return CreateResult{}, serviceError(http.StatusBadRequest, "VALIDATION_ERROR", "visibility must be private or shared")
	}
	if request.TimeControl == nil {
		request.TimeControl = &domain.TimeControl{Minutes: 10}
	}
	if request.TimeControl.Minutes < 1 || request.TimeControl.Minutes > 10 {
		return CreateResult{}, serviceError(http.StatusBadRequest, "VALIDATION_ERROR", "timeControl.minutes must be between 1 and 10")
	}

	fingerprint, err := domain.RequestFingerprint(domain.CanonicalCreateRequest{
		CreatorColor: request.CreatorColor,
		TimeControl:  *request.TimeControl,
		Visibility:   request.Visibility,
	})
	if err != nil {
		return CreateResult{}, serviceError(http.StatusInternalServerError, "INTERNAL_ERROR", "Could not fingerprint create request")
	}
	matchID, err := newUUID()
	if err != nil {
		return CreateResult{}, serviceError(http.StatusInternalServerError, "INTERNAL_ERROR", "Could not create match identifier")
	}

	payload := map[string]any{
		"mode":               "multiplayer",
		"timeControl":        request.TimeControl,
		"visibility":         request.Visibility,
		"botLevel":           nil,
		"matchId":            matchID,
		"participants":       []domain.Participant{{UserID: userID, Color: request.CreatorColor}},
		"creationKey":        domain.CreationKey(userID, idempotencyKey),
		"requestFingerprint": fingerprint,
	}
	response, err := s.logic.Create(ctx, payload)
	if err != nil {
		return CreateResult{}, mapLogicError(err)
	}
	if response.State.Mode != "multiplayer" {
		return CreateResult{}, serviceError(http.StatusBadGateway, "UPSTREAM_ERROR", "Game Logic returned a non-multiplayer game")
	}
	if response.State.MatchID == "" || response.State.CreatedAt == "" {
		return CreateResult{}, serviceError(http.StatusBadGateway, "UPSTREAM_ERROR", "Game Logic returned an incomplete create response")
	}
	s.remember(response.State)
	state := response.State
	return CreateResult{
		MatchID:   state.MatchID,
		Status:    "waiting",
		CreatedAt: state.CreatedAt,
		Replayed:  response.StatusCode == http.StatusOK,
	}, nil
}

func (s *Service) Join(ctx context.Context, matchID, userID string) (domain.GameState, error) {
	if !domain.IsUUID(userID) {
		return domain.GameState{}, serviceError(http.StatusUnauthorized, "UNAUTHORIZED", "A valid X-User-Id is required")
	}
	session, err := s.loadSession(ctx, matchID)
	if err != nil {
		return domain.GameState{}, err
	}
	session.mu.Lock()
	defer session.mu.Unlock()

	response, err := s.logic.Get(ctx, session.state.GameID)
	if err != nil {
		return domain.GameState{}, mapLogicError(err)
	}
	s.update(session, response.State)
	state := session.state
	if state.Status != "waiting" {
		return domain.GameState{}, serviceError(http.StatusConflict, "MATCH_NOT_WAITING", "Match is not waiting for an opponent")
	}
	if _, exists := state.SideFor(userID); exists {
		return domain.GameState{}, serviceError(http.StatusConflict, "ALREADY_PARTICIPANT", "The creator cannot join their own match")
	}
	response, err = s.logic.Join(ctx, state.GameID, userID)
	if err != nil {
		return domain.GameState{}, mapLogicError(err)
	}
	s.update(session, response.State)
	s.broadcastState(response.State)
	return response.State, nil
}

func (s *Service) Get(ctx context.Context, matchID, userID string) (domain.GameState, error) {
	if !domain.IsUUID(userID) {
		return domain.GameState{}, serviceError(http.StatusUnauthorized, "UNAUTHORIZED", "A valid X-User-Id is required")
	}
	session, err := s.loadSession(ctx, matchID)
	if err != nil {
		return domain.GameState{}, err
	}
	session.mu.Lock()
	defer session.mu.Unlock()

	response, err := s.logic.Get(ctx, session.state.GameID)
	if err != nil {
		return domain.GameState{}, mapLogicError(err)
	}
	s.update(session, response.State)
	state := session.state
	if _, participant := state.SideFor(userID); !participant && state.Visibility != "shared" {
		return domain.GameState{}, serviceError(http.StatusNotFound, "MATCH_NOT_FOUND", "Match was not found")
	}
	return state, nil
}

func (s *Service) Resign(ctx context.Context, matchID, userID string) (domain.GameState, error) {
	return s.withParticipant(ctx, matchID, userID, func(session *matchSession, state domain.GameState, side string) (domain.GameState, error) {
		if state.Status != "in_progress" {
			return domain.GameState{}, serviceError(http.StatusConflict, "GAME_NOT_IN_PROGRESS", "Game is not in progress")
		}
		response, err := s.logic.Resign(ctx, state.GameID, side)
		if err != nil {
			s.refreshIfFinished(ctx, session, state.GameID, err)
			return domain.GameState{}, mapLogicError(err)
		}
		s.finishUpdate(session, response.State)
		return response.State, nil
	})
}

func (s *Service) SetVisibility(ctx context.Context, matchID, userID, visibility string, expectedVersion int64) (domain.GameState, error) {
	if visibility != "private" && visibility != "shared" {
		return domain.GameState{}, serviceError(http.StatusBadRequest, "VALIDATION_ERROR", "visibility must be private or shared")
	}
	return s.withParticipant(ctx, matchID, userID, func(session *matchSession, state domain.GameState, _ string) (domain.GameState, error) {
		response, err := s.logic.SetVisibility(ctx, state.GameID, visibility, expectedVersion)
		if err != nil {
			s.refreshIfFinished(ctx, session, state.GameID, err)
			return domain.GameState{}, mapLogicError(err)
		}
		s.update(session, response.State)
		s.broadcastState(response.State)
		return response.State, nil
	})
}

func (s *Service) GetForSocket(ctx context.Context, matchID, userID string) (domain.GameState, error) {
	if !domain.IsUUID(userID) {
		return domain.GameState{}, serviceError(http.StatusUnauthorized, "UNAUTHORIZED", "A valid X-User-Id is required")
	}
	session, err := s.loadSession(ctx, matchID)
	if err != nil {
		return domain.GameState{}, err
	}
	session.mu.Lock()
	defer session.mu.Unlock()
	response, err := s.logic.Get(ctx, session.state.GameID)
	if err != nil {
		return domain.GameState{}, mapLogicError(err)
	}
	if _, participant := response.State.SideFor(userID); !participant {
		return domain.GameState{}, serviceError(http.StatusNotFound, "MATCH_NOT_FOUND", "Match was not found")
	}
	s.update(session, response.State)
	if response.State.IsFinished() {
		s.finishUpdate(session, response.State)
	}
	return session.state, nil
}

func (s *Service) Connected(matchID, userID string) {
	session := s.getSession(matchID)
	session.mu.Lock()
	if timer := session.timers[userID]; timer != nil {
		timer.Stop()
		delete(session.timers, userID)
		delete(session.deadlines, userID)
	}
	session.mu.Unlock()
	s.hub.BroadcastExcept(matchID, userID, map[string]string{"type": "opponent_connected"})
}

func (s *Service) HandleSocketMessage(ctx context.Context, matchID, userID string, payload []byte) {
	var message struct {
		Type            string `json:"type"`
		UCI             string `json:"uci"`
		ExpectedVersion *int64 `json:"expectedVersion"`
	}
	if err := json.Unmarshal(payload, &message); err != nil {
		s.sendSocketError(matchID, userID, "VALIDATION_ERROR", "Invalid JSON message")
		return
	}
	switch message.Type {
	case "ping":
		s.hub.SendTo(matchID, userID, map[string]string{"type": "pong"})
	case "move":
		s.handleMove(ctx, matchID, userID, message.UCI, message.ExpectedVersion)
	case "resign":
		if _, err := s.Resign(ctx, matchID, userID); err != nil {
			s.sendSocketServiceError(matchID, userID, err)
		}
	case "draw_offer", "draw_accept", "draw_decline", "draw_cancel":
		s.handleDraw(ctx, matchID, userID, message.Type)
	default:
		s.sendSocketError(matchID, userID, "VALIDATION_ERROR", "Unknown message type")
	}
}

func (s *Service) Disconnected(matchID, userID string) {
	session := s.getSession(matchID)
	session.mu.Lock()
	defer session.mu.Unlock()
	if s.hub.IsConnected(matchID, userID) || session.state.IsFinished() {
		return
	}
	var reconnectDeadline any
	if session.state.Status == "in_progress" && session.state.IsPlayersTurn(userID) {
		if session.timers[userID] == nil {
			deadline := time.Now().Add(s.reconnectWindow)
			session.deadlines[userID] = deadline
			session.timers[userID] = time.AfterFunc(s.reconnectWindow, func() {
				s.expireReconnect(matchID, userID)
			})
		}
		if deadline, ok := session.deadlines[userID]; ok {
			reconnectDeadline = deadline.UTC().Format(time.RFC3339)
		}
	}
	s.hub.BroadcastExcept(matchID, userID, map[string]any{
		"type":              "opponent_disconnected",
		"reconnectDeadline": reconnectDeadline,
	})
}

func (s *Service) HandleGameFinished(ctx context.Context, eventID, matchID string) error {
	if !domain.IsUUID(eventID) || !domain.IsUUID(matchID) {
		return errors.New("invalid game.finished event identifiers")
	}
	s.mu.Lock()
	if _, exists := s.processedEvent[eventID]; exists {
		s.mu.Unlock()
		return nil
	}
	s.mu.Unlock()

	session, err := s.loadSession(ctx, matchID)
	if err != nil {
		return err
	}
	session.mu.Lock()
	defer session.mu.Unlock()
	response, err := s.logic.Get(ctx, session.state.GameID)
	if err != nil {
		return err
	}
	if response.State.MatchID != matchID || response.State.Mode != "multiplayer" || !response.State.IsFinished() {
		return errors.New("game.finished event did not refer to a finished multiplayer game")
	}
	s.finishUpdate(session, response.State)
	s.mu.Lock()
	s.processedEvent[eventID] = struct{}{}
	s.mu.Unlock()
	return nil
}

func (s *Service) handleMove(ctx context.Context, matchID, userID, uci string, expectedVersion *int64) {
	if strings.TrimSpace(uci) == "" || expectedVersion == nil || *expectedVersion < 0 {
		s.sendSocketError(matchID, userID, "VALIDATION_ERROR", "move requires uci and expectedVersion")
		return
	}
	session, err := s.loadSession(ctx, matchID)
	if err != nil {
		s.sendSocketServiceError(matchID, userID, err)
		return
	}
	session.mu.Lock()
	defer session.mu.Unlock()

	state := session.state
	if _, participant := state.SideFor(userID); !participant {
		s.sendSocketError(matchID, userID, "MATCH_NOT_FOUND", "Match was not found")
		return
	}
	if state.Status != "in_progress" || state.IsFinished() {
		s.sendSocketError(matchID, userID, "GAME_NOT_IN_PROGRESS", "Game is not in progress")
		return
	}
	if !state.IsPlayersTurn(userID) {
		s.sendSocketError(matchID, userID, "NOT_YOUR_TURN", "It is not your turn")
		return
	}
	if *expectedVersion != state.Version {
		s.hub.SendTo(matchID, userID, map[string]any{
			"type": "move_rejected", "code": "VERSION_CONFLICT", "message": "Game state is out of date",
		})
		return
	}
	response, err := s.logic.Move(ctx, state.GameID, strings.ToLower(strings.TrimSpace(uci)), *expectedVersion)
	if err != nil {
		s.refreshIfFinished(ctx, session, state.GameID, err)
		s.sendSocketLogicError(matchID, userID, err, true)
		return
	}
	s.finishUpdate(session, response.State)
}

func (s *Service) handleDraw(ctx context.Context, matchID, userID, messageType string) {
	session, err := s.loadSession(ctx, matchID)
	if err != nil {
		s.sendSocketServiceError(matchID, userID, err)
		return
	}
	session.mu.Lock()
	defer session.mu.Unlock()

	state := session.state
	side, participant := state.SideFor(userID)
	if !participant {
		s.sendSocketError(matchID, userID, "MATCH_NOT_FOUND", "Match was not found")
		return
	}
	if state.Status != "in_progress" {
		s.sendSocketError(matchID, userID, "GAME_NOT_IN_PROGRESS", "Game is not in progress")
		return
	}
	operation, eventType := "", ""
	switch messageType {
	case "draw_offer":
		operation, eventType = "offer", "draw_offered"
		if state.DrawOffer != nil {
			s.sendSocketError(matchID, userID, "DRAW_ALREADY_OFFERED", "A draw offer is already pending")
			return
		}
	case "draw_accept":
		operation = "accept"
		if state.DrawOffer == nil || *state.DrawOffer == side {
			s.sendSocketError(matchID, userID, "DRAW_NOT_ALLOWED", "Only the opponent may accept a pending draw offer")
			return
		}
	case "draw_decline":
		operation, eventType = "decline", "draw_declined"
		if state.DrawOffer == nil || *state.DrawOffer == side {
			s.sendSocketError(matchID, userID, "DRAW_NOT_ALLOWED", "Only the opponent may decline a pending draw offer")
			return
		}
	case "draw_cancel":
		operation, eventType = "cancel", "draw_cancelled"
		if state.DrawOffer == nil || *state.DrawOffer != side {
			s.sendSocketError(matchID, userID, "DRAW_NOT_ALLOWED", "Only the offer creator may cancel the draw offer")
			return
		}
	}
	response, err := s.logic.Draw(ctx, state.GameID, operation, side)
	if err != nil {
		s.refreshIfFinished(ctx, session, state.GameID, err)
		s.sendSocketLogicError(matchID, userID, err, false)
		return
	}
	s.update(session, response.State)
	s.broadcastState(response.State)
	if messageType == "draw_offer" {
		s.hub.Broadcast(matchID, map[string]any{"type": eventType, "by": side})
	} else if eventType != "" {
		s.hub.Broadcast(matchID, map[string]string{"type": eventType})
	}
	if response.State.IsFinished() {
		s.broadcastGameOver(response.State)
		s.cancelTimers(session)
	}
}

func (s *Service) expireReconnect(matchID, userID string) {
	session := s.getSession(matchID)
	session.mu.Lock()
	defer session.mu.Unlock()
	delete(session.timers, userID)
	delete(session.deadlines, userID)
	if s.hub.IsConnected(matchID, userID) || session.state.Status != "in_progress" ||
		session.state.IsFinished() || !session.state.IsPlayersTurn(userID) {
		return
	}
	side, ok := session.state.SideFor(userID)
	if !ok {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	response, err := s.logic.Abandon(ctx, session.state.GameID, side)
	if err != nil {
		if s.refreshIfFinished(ctx, session, session.state.GameID, err) {
			return
		}
		s.logger.Error("reconnect deadline abandonment failed", "matchId", matchID, "userId", userID, "error", err)
		s.hub.Broadcast(matchID, map[string]any{"type": "error", "code": "SERVICES_UNAVAILABLE", "message": "Could not close the game after the reconnect deadline"})
		return
	}
	s.finishUpdate(session, response.State)
}

func (s *Service) withParticipant(ctx context.Context, matchID, userID string, action func(*matchSession, domain.GameState, string) (domain.GameState, error)) (domain.GameState, error) {
	if !domain.IsUUID(userID) {
		return domain.GameState{}, serviceError(http.StatusUnauthorized, "UNAUTHORIZED", "A valid X-User-Id is required")
	}
	session, err := s.loadSession(ctx, matchID)
	if err != nil {
		return domain.GameState{}, err
	}
	session.mu.Lock()
	defer session.mu.Unlock()
	side, ok := session.state.SideFor(userID)
	if !ok {
		return domain.GameState{}, serviceError(http.StatusNotFound, "MATCH_NOT_FOUND", "Match was not found")
	}
	return action(session, session.state, side)
}

func (s *Service) loadSession(ctx context.Context, matchID string) (*matchSession, error) {
	if !domain.IsUUID(matchID) {
		return nil, serviceError(http.StatusNotFound, "MATCH_NOT_FOUND", "Match was not found")
	}
	session := s.getSession(matchID)
	session.mu.Lock()
	defer session.mu.Unlock()
	if session.loaded {
		return session, nil
	}

	s.mu.Lock()
	gameID := s.matchToGame[matchID]
	s.mu.Unlock()
	var response gamelogic.Response
	var err error
	if gameID != "" {
		response, err = s.logic.Get(ctx, gameID)
	} else {
		response, err = s.logic.GetByMatch(ctx, matchID)
	}
	if err != nil {
		return nil, mapLogicError(err)
	}
	if response.State.MatchID != matchID {
		return nil, serviceError(http.StatusNotFound, "MATCH_NOT_FOUND", "Match was not found")
	}
	s.update(session, response.State)
	return session, nil
}

func (s *Service) getSession(matchID string) *matchSession {
	s.mu.Lock()
	defer s.mu.Unlock()
	session := s.sessions[matchID]
	if session == nil {
		session = &matchSession{timers: make(map[string]*time.Timer), deadlines: make(map[string]time.Time)}
		s.sessions[matchID] = session
	}
	return session
}

func (s *Service) remember(state domain.GameState) {
	session := s.getSession(state.MatchID)
	session.mu.Lock()
	s.update(session, state)
	session.mu.Unlock()
}

func (s *Service) update(session *matchSession, state domain.GameState) {
	session.state = state
	session.loaded = true
	s.mu.Lock()
	s.matchToGame[state.MatchID] = state.GameID
	s.mu.Unlock()
}

func (s *Service) finishUpdate(session *matchSession, state domain.GameState) {
	s.update(session, state)
	s.broadcastState(state)
	if state.IsFinished() {
		s.broadcastGameOver(state)
		s.cancelTimers(session)
	}
}

func (s *Service) cancelTimers(session *matchSession) {
	for userID, timer := range session.timers {
		timer.Stop()
		delete(session.timers, userID)
		delete(session.deadlines, userID)
	}
}

func (s *Service) broadcastState(state domain.GameState) {
	message := map[string]any{"type": "state", "state": state.Raw}
	if move := state.LastMove(); move != "" {
		message["lastMove"] = move
	}
	s.hub.Broadcast(state.MatchID, message)
}

func (s *Service) broadcastGameOver(state domain.GameState) {
	s.hub.Broadcast(state.MatchID, map[string]any{
		"type": "game_over", "result": state.Result, "endReason": state.EndReason,
	})
}

func (s *Service) sendSocketError(matchID, userID, code, message string) {
	s.hub.SendTo(matchID, userID, map[string]string{"type": "error", "code": code, "message": message})
}

func (s *Service) sendSocketServiceError(matchID, userID string, err error) {
	var serviceErr *ServiceError
	if errors.As(err, &serviceErr) {
		s.sendSocketError(matchID, userID, serviceErr.Code, serviceErr.Message)
		return
	}
	s.sendSocketError(matchID, userID, "SERVICES_UNAVAILABLE", "A required service is unavailable")
}

func (s *Service) refreshIfFinished(ctx context.Context, session *matchSession, gameID string, actionErr error) bool {
	var logicErr *gamelogic.APIError
	if !errors.As(actionErr, &logicErr) {
		return false
	}
	switch logicErr.Code {
	case "GAME_FINISHED", "GAME_NOT_IN_PROGRESS", "VERSION_CONFLICT", "CLOCK_EXPIRED":
	default:
		return false
	}
	response, err := s.logic.Get(ctx, gameID)
	if err != nil {
		s.logger.Error("could not refresh finished game", "gameId", gameID, "error", err)
		return false
	}
	s.finishUpdate(session, response.State)
	return response.State.IsFinished()
}

func (s *Service) sendSocketLogicError(matchID, userID string, err error, isMove bool) {
	var logicErr *gamelogic.APIError
	if errors.As(err, &logicErr) {
		if isMove {
			s.hub.SendTo(matchID, userID, map[string]string{"type": "move_rejected", "code": logicErr.Code, "message": logicErr.Message})
			return
		}
		s.sendSocketError(matchID, userID, logicErr.Code, logicErr.Message)
		return
	}
	s.sendSocketError(matchID, userID, "SERVICES_UNAVAILABLE", "A required service is unavailable")
}

func mapLogicError(err error) error {
	var apiErr *gamelogic.APIError
	if !errors.As(err, &apiErr) {
		return serviceError(http.StatusServiceUnavailable, "SERVICES_UNAVAILABLE", "Game Logic is unavailable")
	}
	switch apiErr.Code {
	case "GAME_NOT_FOUND":
		return serviceError(http.StatusNotFound, "MATCH_NOT_FOUND", apiErr.Message)
	case "GAME_NOT_WAITING":
		return serviceError(http.StatusConflict, "MATCH_NOT_WAITING", apiErr.Message)
	case "ALREADY_PARTICIPANT":
		return serviceError(http.StatusConflict, "ALREADY_PARTICIPANT", apiErr.Message)
	case "IDEMPOTENCY_KEY_REUSED":
		return serviceError(http.StatusConflict, "IDEMPOTENCY_KEY_REUSED", apiErr.Message)
	}
	if apiErr.StatusCode == http.StatusServiceUnavailable || apiErr.StatusCode == http.StatusBadGateway || apiErr.StatusCode == http.StatusGatewayTimeout {
		return serviceError(http.StatusServiceUnavailable, "SERVICES_UNAVAILABLE", "Game Logic is unavailable")
	}
	return serviceError(apiErr.StatusCode, apiErr.Code, apiErr.Message)
}

func serviceError(status int, code, message string) *ServiceError {
	return &ServiceError{StatusCode: status, Code: code, Message: message}
}

func newUUID() (string, error) {
	var value [16]byte
	if _, err := rand.Read(value[:]); err != nil {
		return "", fmt.Errorf("generate UUID: %w", err)
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	encoded := hex.EncodeToString(value[:])
	return encoded[:8] + "-" + encoded[8:12] + "-" + encoded[12:16] + "-" + encoded[16:20] + "-" + encoded[20:], nil
}
