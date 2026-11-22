package service

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"insightfulgames/multiplayer-component/internal/domain"
	"insightfulgames/multiplayer-component/internal/gamelogic"
	"insightfulgames/multiplayer-component/internal/realtime"
)

// Logic son las llamadas a Game Logic que le quedan al hub: releer una partida (por id o por matchId) y
// abandonar cuando vence el plazo de reconexión. Todo lo demás (crear, unirse, jugar, rendirse, tablas,
// visibilidad) lo orquesta el gateway.
type Logic interface {
	Get(context.Context, string) (gamelogic.Response, error)
	GetByMatch(context.Context, string) (gamelogic.Response, error)
	Abandon(context.Context, string, string) (gamelogic.Response, error)
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

// PublishRequest es el aviso del gateway tras operar en Game Logic (crear/unirse/rendirse/visibilidad).
type PublishRequest struct {
	// State es el GameState vigente tal como lo entregó Game Logic.
	State json.RawMessage `json:"state"`
	// GameOver false evita el game_over aunque la partida haya terminado (p. ej. al cambiar la visibilidad
	// de una partida terminada); por omisión se envía.
	GameOver *bool `json:"gameOver"`
	// Events son avisos de tablas (draw_offered con `by`, draw_declined, draw_cancelled) que se envían
	// después del state y antes de game_over.
	Events []map[string]any `json:"events"`
}

var allowedPublishEvents = map[string]struct{}{
	"draw_offered": {}, "draw_declined": {}, "draw_cancelled": {},
}

// ApplyPublish actualiza la sesión con el estado que el gateway ya guardó en Game Logic y lo envía a los
// clientes conectados: state y, si terminó, game_over, cancelando los plazos de reconexión. No consulta a
// nadie. Un state con una version menor que la que ya tiene la sesión se ignora: un aviso atrasado no debe
// hacer retroceder a la sesión ni a los clientes (el expectedVersion de Game Logic es la guarda real).
func (s *Service) ApplyPublish(matchID string, request PublishRequest) error {
	if !domain.IsUUID(matchID) {
		return serviceError(http.StatusNotFound, "MATCH_NOT_FOUND", "Match was not found")
	}
	if len(request.State) == 0 {
		return serviceError(http.StatusBadRequest, "VALIDATION_ERROR", "state is required")
	}
	state, err := domain.DecodeGameState(request.State)
	if err != nil {
		return serviceError(http.StatusBadRequest, "VALIDATION_ERROR", "state is not a valid GameState")
	}
	for _, event := range request.Events {
		eventType, _ := event["type"].(string)
		if _, allowed := allowedPublishEvents[eventType]; !allowed {
			return serviceError(http.StatusBadRequest, "VALIDATION_ERROR", "events contains an unsupported event type")
		}
	}
	if state.MatchID != matchID {
		return serviceError(http.StatusBadRequest, "VALIDATION_ERROR", "state.matchId does not match the route")
	}

	session := s.getSession(matchID)
	session.mu.Lock()
	defer session.mu.Unlock()
	if session.loaded && state.Version < session.state.Version {
		s.logger.Debug("stale publish ignored", "matchId", matchID, "version", state.Version, "current", session.state.Version)
		return nil
	}
	s.update(session, state)
	s.broadcastState(state)
	for _, event := range request.Events {
		s.hub.Broadcast(matchID, event)
	}
	if state.IsFinished() {
		if request.GameOver == nil || *request.GameOver {
			s.broadcastGameOver(state)
		}
		s.cancelTimers(session)
	}
	return nil
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

// HandleSocketMessage atiende los mensajes del cliente que llegan al hub. Solo `ping`: el resto de las
// acciones (move, resign, draw_*) las atiende el gateway, que opera en Game Logic y publica el resultado.
func (s *Service) HandleSocketMessage(_ context.Context, matchID, userID string, payload []byte) {
	var message struct {
		Type string `json:"type"`
	}
	if err := json.Unmarshal(payload, &message); err != nil {
		return
	}
	if message.Type == "ping" {
		s.hub.SendTo(matchID, userID, map[string]string{"type": "pong"})
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

// refreshIfFinished relee la partida tras un fallo del abandono por el timer: si ya terminó por otra vía,
// actualiza la sesión y avisa a los clientes.
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
