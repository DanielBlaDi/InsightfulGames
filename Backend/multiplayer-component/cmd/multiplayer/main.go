package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"insightfulgames/multiplayer-component/internal/config"
	"insightfulgames/multiplayer-component/internal/gamelogic"
	"insightfulgames/multiplayer-component/internal/httpapi"
	"insightfulgames/multiplayer-component/internal/messaging"
	"insightfulgames/multiplayer-component/internal/realtime"
	"insightfulgames/multiplayer-component/internal/service"
)

func main() {
	healthCheck := flag.Bool("health", false, "check whether the local service is healthy")
	flag.Parse()
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg, err := config.Load()
	if err != nil {
		logger.Error("invalid configuration", "error", err)
		os.Exit(1)
	}
	logger = slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: cfg.LogLevel}))
	if *healthCheck {
		checkHealth(cfg.Port)
		return
	}

	gameClient := gamelogic.NewClient(cfg.GatewayInternalURL, cfg.RequestTimeout)
	hub := realtime.NewHub()
	app := service.New(gameClient, hub, cfg.ReconnectWindow, logger)
	handler := httpapi.New(app, hub, cfg.AllowedOrigins, logger)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	consumer := messaging.NewConsumer(cfg.RabbitMQURL, app, logger)
	go consumer.Run(ctx)

	server := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       90 * time.Second,
	}

	go func() {
		logger.Info("multiplayer service listening", "port", cfg.Port)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("HTTP server failed", "error", err)
			stop()
		}
	}()

	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		logger.Error("HTTP server shutdown failed", "error", err)
	}
}

func checkHealth(port string) {
	client := &http.Client{Timeout: 2 * time.Second}
	response, err := client.Get("http://127.0.0.1:" + port + "/health")
	if err != nil {
		os.Exit(1)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		os.Exit(1)
	}
	var body struct {
		Status string `json:"status"`
	}
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil || body.Status != "ok" {
		os.Exit(1)
	}
}
