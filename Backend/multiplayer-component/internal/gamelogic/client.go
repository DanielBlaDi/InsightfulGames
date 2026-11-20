package gamelogic

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"insightfulgames/multiplayer-component/internal/domain"
)

type Client struct {
	baseURL string
	http    *http.Client
}

type Response struct {
	State      domain.GameState
	StatusCode int
}

type APIError struct {
	StatusCode int
	Code       string
	Message    string
}

func (e *APIError) Error() string {
	return fmt.Sprintf("Game Logic returned %d %s: %s", e.StatusCode, e.Code, e.Message)
}

func NewClient(baseURL string, timeout time.Duration) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		http:    &http.Client{Timeout: timeout},
	}
}

func (c *Client) Create(ctx context.Context, payload any) (Response, error) {
	return c.request(ctx, http.MethodPost, "/internal/logic/games", payload)
}

func (c *Client) Join(ctx context.Context, gameID, userID string) (Response, error) {
	return c.request(ctx, http.MethodPost, gamePath(gameID, "/join"), map[string]string{"userId": userID})
}

func (c *Client) Get(ctx context.Context, gameID string) (Response, error) {
	return c.request(ctx, http.MethodGet, gamePath(gameID, ""), nil)
}

func (c *Client) GetByMatch(ctx context.Context, matchID string) (Response, error) {
	return c.request(ctx, http.MethodGet, "/internal/logic/games/by-match/"+url.PathEscape(matchID), nil)
}

func (c *Client) Move(ctx context.Context, gameID, uci string, expectedVersion int64) (Response, error) {
	return c.request(ctx, http.MethodPost, gamePath(gameID, "/moves"), map[string]any{
		"uci":             uci,
		"expectedVersion": expectedVersion,
	})
}

func (c *Client) Resign(ctx context.Context, gameID, side string) (Response, error) {
	return c.request(ctx, http.MethodPost, gamePath(gameID, "/resign"), map[string]string{"side": side})
}

func (c *Client) Abandon(ctx context.Context, gameID, side string) (Response, error) {
	return c.request(ctx, http.MethodPost, gamePath(gameID, "/abandon"), map[string]string{"side": side})
}

func (c *Client) Draw(ctx context.Context, gameID, operation, side string) (Response, error) {
	return c.request(ctx, http.MethodPost, gamePath(gameID, "/draw/"+operation), map[string]string{"side": side})
}

func (c *Client) SetVisibility(ctx context.Context, gameID, visibility string, expectedVersion int64) (Response, error) {
	return c.request(ctx, http.MethodPatch, gamePath(gameID, "/visibility"), map[string]any{
		"visibility":      visibility,
		"expectedVersion": expectedVersion,
	})
}

func gamePath(gameID, suffix string) string {
	return "/internal/logic/games/" + url.PathEscape(gameID) + suffix
}

func (c *Client) request(ctx context.Context, method, path string, body any) (Response, error) {
	var requestBody io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return Response{}, fmt.Errorf("encode Game Logic request: %w", err)
		}
		requestBody = bytes.NewReader(encoded)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, requestBody)
	if err != nil {
		return Response{}, fmt.Errorf("create Game Logic request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	response, err := c.http.Do(req)
	if err != nil {
		return Response{}, fmt.Errorf("call Game Logic: %w", err)
	}
	defer response.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(response.Body, 2<<20))
	if err != nil {
		return Response{}, fmt.Errorf("read Game Logic response: %w", err)
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		var envelope domain.ErrorEnvelope
		if err := json.Unmarshal(raw, &envelope); err != nil {
			return Response{}, &APIError{StatusCode: response.StatusCode, Code: "UPSTREAM_ERROR", Message: "Game Logic returned an invalid error response"}
		}
		return Response{}, &APIError{
			StatusCode: response.StatusCode,
			Code:       envelope.Error.Code,
			Message:    envelope.Error.Message,
		}
	}

	state, err := domain.DecodeGameState(raw)
	if err != nil {
		return Response{}, fmt.Errorf("decode Game Logic response: %w", err)
	}
	return Response{State: state, StatusCode: response.StatusCode}, nil
}
