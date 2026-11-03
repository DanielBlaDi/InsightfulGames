package config

import (
	"fmt"
	"log/slog"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Port               string
	GatewayInternalURL string
	RabbitMQURL        string
	LogLevel           slog.Level
	ReconnectWindow    time.Duration
	RequestTimeout     time.Duration
	AllowedOrigins     map[string]struct{}
}

func Load() (Config, error) {
	logLevel, err := parseLogLevel(valueOr("LOG_LEVEL", "INFO"))
	if err != nil {
		return Config{}, err
	}
	cfg := Config{
		Port:               valueOr("PORT", "8084"),
		GatewayInternalURL: valueOr("GATEWAY_INTERNAL_URL", "http://api-gateway-component:8080"),
		RabbitMQURL:        strings.TrimSpace(os.Getenv("RABBITMQ_URL")),
		LogLevel:           logLevel,
		RequestTimeout:     5 * time.Second,
		AllowedOrigins:     parseOrigins(os.Getenv("WS_ALLOWED_ORIGINS")),
	}

	if port, err := strconv.Atoi(cfg.Port); err != nil || port < 1 || port > 65535 {
		return Config{}, fmt.Errorf("PORT must be an integer from 1 to 65535")
	}
	if !strings.HasPrefix(cfg.GatewayInternalURL, "http://") && !strings.HasPrefix(cfg.GatewayInternalURL, "https://") {
		return Config{}, fmt.Errorf("GATEWAY_INTERNAL_URL must be an http or https URL")
	}
	if cfg.RabbitMQURL == "" {
		return Config{}, fmt.Errorf("RABBITMQ_URL is required")
	}

	seconds := 30
	if raw := strings.TrimSpace(os.Getenv("RECONNECT_WINDOW_SECONDS")); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 || parsed > 600 {
			return Config{}, fmt.Errorf("RECONNECT_WINDOW_SECONDS must be an integer from 1 to 600")
		}
		seconds = parsed
	}
	cfg.ReconnectWindow = time.Duration(seconds) * time.Second
	return cfg, nil
}

func parseLogLevel(value string) (slog.Level, error) {
	switch strings.ToUpper(strings.TrimSpace(value)) {
	case "DEBUG":
		return slog.LevelDebug, nil
	case "INFO":
		return slog.LevelInfo, nil
	case "WARN", "WARNING":
		return slog.LevelWarn, nil
	case "ERROR":
		return slog.LevelError, nil
	default:
		return 0, fmt.Errorf("LOG_LEVEL must be DEBUG, INFO, WARN, or ERROR")
	}
}

func valueOr(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func parseOrigins(raw string) map[string]struct{} {
	origins := make(map[string]struct{})
	for _, origin := range strings.Split(raw, ",") {
		if origin = strings.TrimSpace(origin); origin != "" {
			origins[origin] = struct{}{}
		}
	}
	return origins
}
