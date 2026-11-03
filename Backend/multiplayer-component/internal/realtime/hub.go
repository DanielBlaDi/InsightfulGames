package realtime

import (
	"encoding/json"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

const outboundBufferSize = 32

type Client struct {
	UserID string
	Send   chan []byte
	Done   chan struct{}
	socket *websocket.Conn
	once   sync.Once
}

func NewClient(userID string, socket *websocket.Conn) *Client {
	return &Client{
		UserID: userID,
		Send:   make(chan []byte, outboundBufferSize),
		Done:   make(chan struct{}),
		socket: socket,
	}
}

func (c *Client) Socket() *websocket.Conn {
	return c.socket
}

func (c *Client) Close(code int, reason string) {
	c.once.Do(func() {
		_ = c.socket.WriteControl(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(code, reason),
			time.Now().Add(time.Second),
		)
		close(c.Done)
		_ = c.socket.Close()
	})
}

type Hub struct {
	mu      sync.RWMutex
	clients map[string]map[string]*Client
}

func NewHub() *Hub {
	return &Hub{clients: make(map[string]map[string]*Client)}
}

func (h *Hub) Add(matchID string, client *Client) *Client {
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.clients[matchID] == nil {
		h.clients[matchID] = make(map[string]*Client)
	}
	previous := h.clients[matchID][client.UserID]
	h.clients[matchID][client.UserID] = client
	return previous
}

func (h *Hub) Remove(matchID string, client *Client) bool {
	h.mu.Lock()
	defer h.mu.Unlock()
	byUser := h.clients[matchID]
	if byUser[client.UserID] != client {
		return false
	}
	delete(byUser, client.UserID)
	if len(byUser) == 0 {
		delete(h.clients, matchID)
	}
	return true
}

func (h *Hub) IsConnected(matchID, userID string) bool {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return h.clients[matchID][userID] != nil
}

func (h *Hub) SendTo(matchID, userID string, message any) {
	encoded, err := json.Marshal(message)
	if err != nil {
		return
	}
	h.mu.RLock()
	client := h.clients[matchID][userID]
	if client != nil {
		select {
		case <-client.Done:
		case client.Send <- encoded:
		default:
			go client.Close(websocket.ClosePolicyViolation, "client is not consuming messages")
		}
	}
	h.mu.RUnlock()
}

func (h *Hub) Broadcast(matchID string, message any) {
	h.broadcast(matchID, "", message)
}

func (h *Hub) BroadcastExcept(matchID, excludedUserID string, message any) {
	h.broadcast(matchID, excludedUserID, message)
}

func (h *Hub) broadcast(matchID, excludedUserID string, message any) {
	encoded, err := json.Marshal(message)
	if err != nil {
		return
	}
	h.mu.RLock()
	defer h.mu.RUnlock()
	for userID, client := range h.clients[matchID] {
		if userID == excludedUserID {
			continue
		}
		select {
		case <-client.Done:
		case client.Send <- encoded:
		default:
			go client.Close(websocket.ClosePolicyViolation, "client is not consuming messages")
		}
	}
}

func (h *Hub) CloseMatch(matchID string, code int, reason string) {
	h.mu.Lock()
	clients := h.clients[matchID]
	delete(h.clients, matchID)
	h.mu.Unlock()
	for _, client := range clients {
		client.Close(code, reason)
	}
}
