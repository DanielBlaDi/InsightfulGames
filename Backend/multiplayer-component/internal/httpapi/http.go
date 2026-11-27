
package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"time"

	"insightfulgames/multiplayer-component/internal/domain"
	"insightfulgames/multiplayer-component/internal/realtime"
	"insightfulgames/multiplayer-component/internal/service"

	"github.com/gorilla/websocket"
)

type API struct {
	service        *service.Service
	hub            *realtime.Hub
	allowedOrigins map[string]struct{}
	logger         *slog.Logger
	upgrader       websocket.Upgrader
}

func New(app *service.Service, hub *realtime.Hub, allowedOrigins map[string]struct{}, logger *slog.Logger) http.Handler {
	api := &API{
		service:        app,
		hub:            hub,
		allowedOrigins: allowedOrigins,
		logger:         logger,
	}
	api.upgrader = websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
		CheckOrigin:     api.originAllowed,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", api.health)
	// Crear, unirse, leer, rendirse y cambiar la visibilidad las orquesta el gateway contra Game Logic;
	// aquí solo llega el aviso para los clientes conectados.
	mux.HandleFunc("POST /internal/multiplayer/matches/{id}/publish", api.publish)
	mux.HandleFunc("GET /internal/multiplayer/ws/matches/{id}", api.websocket)
	mux.HandleFunc("/", func(w http.ResponseWriter, _ *http.Request) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "Route was not found")
	})
	return mux
}

func (a *API) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// publish: el gateway ya operó en Game Logic y avisa. El hub actualiza la sesión y envía a los clientes.
func (a *API) publish(w http.ResponseWriter, r *http.Request) {
	var request service.PublishRequest
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4<<20))
	if err := decoder.Decode(&request); err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid JSON request body")
		return
	}
	if err := a.service.ApplyPublish(r.PathValue("id"), request); err != nil {
		writeServiceError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (a *API) websocket(w http.ResponseWriter, r *http.Request) {
	conn, err := a.upgrader.Upgrade(w, r, nil)
	if err != nil {
		a.logger.Warn("WebSocket upgrade failed", "matchId", r.PathValue("id"), "error", err)
		return
	}

	userID := r.Header.Get("X-User-Id")
	if userID == "" {
		closeSocket(conn, 4401, "invalid session")
		return
	}
	matchID := r.PathValue("id")
	state, err := a.service.GetForSocket(r.Context(), matchID, userID)
	if err != nil {
		code, reason := socketCloseForError(err)
		closeSocket(conn, code, reason)
		return
	}
	client := realtime.NewClient(userID, conn)
	if previous := a.hub.Add(matchID, client); previous != nil {
		previous.Close(websocket.CloseNormalClosure, "reconnected")
	}
	if !state.IsFinished() {
		a.service.Connected(matchID, userID)
	}
	a.hub.SendTo(matchID, userID, map[string]any{"type": "state", "state": state.Raw})
	if state.IsFinished() {
		a.hub.SendTo(matchID, userID, map[string]any{"type": "game_over", "result": state.Result, "endReason": state.EndReason})
		go func() {
			a.writePump(client)
			a.hub.Remove(matchID, client)
		}()
		return
	}
	go a.writePump(client)
	a.readPump(r.Context(), matchID, client)
}

func (a *API) readPump(ctx context.Context, matchID string, client *realtime.Client) {
	defer func() {
		client.Close(websocket.CloseNormalClosure, "")
		if a.hub.Remove(matchID, client) {
			a.service.Disconnected(matchID, client.UserID)
		}
	}()
	conn := client.Socket()
	conn.SetReadLimit(8 << 10)
	_ = conn.SetReadDeadline(time.Now().Add(90 * time.Second))
	conn.SetPongHandler(func(string) error {
		return conn.SetReadDeadline(time.Now().Add(90 * time.Second))
	})
	for {
		_, payload, err := conn.ReadMessage()
		if err != nil {
			return
		}
		a.service.HandleSocketMessage(ctx, matchID, client.UserID, payload)
	}
}

func (a *API) writePump(client *realtime.Client) {
	conn := client.Socket()
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-client.Done:
			return
		case payload := <-client.Send:
			_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := conn.WriteMessage(websocket.TextMessage, payload); err != nil {
				client.Close(websocket.CloseGoingAway, "write failed")
				return
			}
			var message struct {
				Type string `json:"type"`
			}
			if json.Unmarshal(payload, &message) == nil && message.Type == "game_over" {
				client.Close(websocket.CloseNormalClosure, "game finished")
				return
			}
		case <-ticker.C:
			_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				client.Close(websocket.CloseGoingAway, "ping failed")
				return
			}
		}
	}
}

func (a *API) originAllowed(r *http.Request) bool {
	origin := r.Header.Get("Origin")
	if origin == "" || len(a.allowedOrigins) == 0 {
		return true
	}
	_, allowed := a.allowedOrigins[origin]
	return allowed
}

func writeServiceError(w http.ResponseWriter, err error) {
	var serviceErr *service.ServiceError
	if errors.As(err, &serviceErr) {
		writeError(w, serviceErr.StatusCode, serviceErr.Code, serviceErr.Message)
		return
	}
	writeError(w, http.StatusServiceUnavailable, "SERVICES_UNAVAILABLE", "A required service is unavailable")
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, domain.ErrorEnvelope{Error: domain.APIError{Code: code, Message: message}})
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if raw, ok := body.(json.RawMessage); ok {
		_, _ = w.Write(raw)
		return
	}
	if err := json.NewEncoder(w).Encode(body); err != nil {
		return
	}
}

func closeSocket(conn *websocket.Conn, code int, reason string) {
	_ = conn.WriteControl(websocket.CloseMessage, websocket.FormatCloseMessage(code, reason), time.Now().Add(time.Second))
	_ = conn.Close()
}

func socketCloseForError(err error) (int, string) {
	var serviceErr *service.ServiceError
	if errors.As(err, &serviceErr) {
		switch serviceErr.Code {
		case "UNAUTHORIZED":
			return 4401, "invalid session"
		case "MATCH_NOT_FOUND":
			return 4404, "match not found or user is not a participant"
		}
	}
	return websocket.CloseInternalServerErr, "service unavailable"
}
