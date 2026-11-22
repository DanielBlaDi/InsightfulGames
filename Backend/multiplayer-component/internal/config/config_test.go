package config

import (
	"log/slog"
	"testing"
)

func TestLoadUsesContractDefaults(t *testing.T) {
	t.Setenv("PORT", "")
	t.Setenv("GAME_LOGIC_URL", "")
	t.Setenv("RABBITMQ_URL", "amqp://localhost:5672/")
	t.Setenv("LOG_LEVEL", "")
	t.Setenv("RECONNECT_WINDOW_SECONDS", "")
	t.Setenv("WS_ALLOWED_ORIGINS", "")

	cfg, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Port != "8084" || cfg.GameLogicURL != "http://game-logic-component:8082" {
		t.Fatalf("configuration defaults = port %q, game logic %q", cfg.Port, cfg.GameLogicURL)
	}
	if cfg.LogLevel != slog.LevelInfo || cfg.ReconnectWindow.Seconds() != 30 {
		t.Fatalf("logging/reconnect defaults = level %v, window %s", cfg.LogLevel, cfg.ReconnectWindow)
	}
}

func TestLoadRequiresRabbitMQAndValidLogLevel(t *testing.T) {
	t.Setenv("PORT", "")
	t.Setenv("GAME_LOGIC_URL", "")
	t.Setenv("RABBITMQ_URL", "")
	t.Setenv("LOG_LEVEL", "")
	t.Setenv("RECONNECT_WINDOW_SECONDS", "")
	t.Setenv("WS_ALLOWED_ORIGINS", "")
	if _, err := Load(); err == nil {
		t.Fatal("Load succeeded without RABBITMQ_URL")
	}

	t.Setenv("RABBITMQ_URL", "amqp://localhost:5672/")
	t.Setenv("LOG_LEVEL", "verbose")
	if _, err := Load(); err == nil {
		t.Fatal("Load succeeded with an unsupported LOG_LEVEL")
	}
}
