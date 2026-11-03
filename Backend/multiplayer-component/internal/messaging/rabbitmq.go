package messaging

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"insightfulgames/multiplayer-component/internal/domain"

	amqp "github.com/rabbitmq/amqp091-go"
)

const (
	exchangeName = "game.events"
	retryName    = "retry.events"
	queueName    = "multiplayer.game-finished"
	routingKey   = "game.finished"
	maxRetries   = int64(5)
)

type gameFinishedHandler interface {
	HandleGameFinished(context.Context, string, string) error
}

type Consumer struct {
	url     string
	handler gameFinishedHandler
	logger  *slog.Logger
}

type gameFinishedEvent struct {
	EventID   string `json:"eventId"`
	EventType string `json:"eventType"`
	MatchID   string `json:"matchId"`
	Mode      string `json:"mode"`
}

func NewConsumer(url string, handler gameFinishedHandler, logger *slog.Logger) *Consumer {
	return &Consumer{url: url, handler: handler, logger: logger}
}

func (c *Consumer) Run(ctx context.Context) {
	for ctx.Err() == nil {
		if err := c.consume(ctx); err != nil && ctx.Err() == nil {
			c.logger.Error("RabbitMQ consumer stopped; reconnecting", "error", err)
			select {
			case <-ctx.Done():
				return
			case <-time.After(5 * time.Second):
			}
		}
	}
}

func (c *Consumer) consume(ctx context.Context) error {
	connection, err := amqp.Dial(c.url)
	if err != nil {
		return fmt.Errorf("connect RabbitMQ: %w", err)
	}
	defer connection.Close()

	channel, err := connection.Channel()
	if err != nil {
		return fmt.Errorf("open RabbitMQ channel: %w", err)
	}
	defer channel.Close()

	if err := declareTopology(channel); err != nil {
		return err
	}
	if err := channel.Confirm(false); err != nil {
		return fmt.Errorf("enable publisher confirms: %w", err)
	}
	confirms := channel.NotifyPublish(make(chan amqp.Confirmation, 1))

	deliveries, err := channel.Consume(queueName, "multiplayer-component", false, false, false, false, nil)
	if err != nil {
		return fmt.Errorf("consume %s: %w", queueName, err)
	}
	c.logger.Info("RabbitMQ consumer ready", "queue", queueName)

	for {
		select {
		case <-ctx.Done():
			return nil
		case delivery, ok := <-deliveries:
			if !ok {
				return errors.New("RabbitMQ delivery channel closed")
			}
			if err := c.process(ctx, channel, confirms, delivery); err != nil {
				c.logger.Error("failed to process game.finished delivery", "error", err)
				if nackErr := delivery.Nack(false, true); nackErr != nil {
					return fmt.Errorf("requeue failed delivery: %w", nackErr)
				}
			}
		}
	}
}

func declareTopology(channel *amqp.Channel) error {
	if err := channel.ExchangeDeclare(exchangeName, amqp.ExchangeTopic, true, false, false, false, nil); err != nil {
		return fmt.Errorf("declare game events exchange: %w", err)
	}
	if err := channel.ExchangeDeclare(retryName, amqp.ExchangeDirect, true, false, false, false, nil); err != nil {
		return fmt.Errorf("declare retry exchange: %w", err)
	}
	if _, err := channel.QueueDeclare(queueName, true, false, false, false, nil); err != nil {
		return fmt.Errorf("declare consumer queue: %w", err)
	}
	waitArgs := amqp.Table{
		"x-message-ttl":             int32(5000),
		"x-dead-letter-exchange":    "",
		"x-dead-letter-routing-key": queueName,
	}
	waitQueue := queueName + ".wait"
	if _, err := channel.QueueDeclare(waitQueue, true, false, false, false, waitArgs); err != nil {
		return fmt.Errorf("declare retry wait queue: %w", err)
	}
	if _, err := channel.QueueDeclare(queueName+".dlq", true, false, false, false, nil); err != nil {
		return fmt.Errorf("declare dead-letter queue: %w", err)
	}
	if err := channel.QueueBind(queueName, routingKey, exchangeName, false, nil); err != nil {
		return fmt.Errorf("bind event queue: %w", err)
	}
	if err := channel.QueueBind(waitQueue, queueName, retryName, false, nil); err != nil {
		return fmt.Errorf("bind retry wait queue: %w", err)
	}
	if err := channel.Qos(1, 0, false); err != nil {
		return fmt.Errorf("configure consumer prefetch: %w", err)
	}
	return nil
}

func (c *Consumer) process(ctx context.Context, channel *amqp.Channel, confirms <-chan amqp.Confirmation, delivery amqp.Delivery) error {
	var event gameFinishedEvent
	if err := json.Unmarshal(delivery.Body, &event); err != nil ||
		event.EventType != "game.finished" || !domain.IsUUID(event.EventID) || event.Mode == "" {
		return c.publishAndAck(ctx, channel, confirms, delivery, queueName+".dlq", nil)
	}
	if event.Mode != "multiplayer" {
		return delivery.Ack(false)
	}
	if !domain.IsUUID(event.MatchID) {
		return c.publishAndAck(ctx, channel, confirms, delivery, queueName+".dlq", nil)
	}
	if err := c.handler.HandleGameFinished(ctx, event.EventID, event.MatchID); err != nil {
		retries, valid := retryCount(delivery.Headers)
		if !valid || retries >= maxRetries {
			c.logger.Error("game.finished message exhausted retries", "eventId", event.EventID, "retryCount", retries, "error", err)
			return c.publishAndAck(ctx, channel, confirms, delivery, queueName+".dlq", nil)
		}
		headers := copyHeaders(delivery.Headers)
		headers["x-retry-count"] = retries + 1
		return c.publishAndAck(ctx, channel, confirms, delivery, retryName, headers)
	}
	return delivery.Ack(false)
}

func (c *Consumer) publishAndAck(ctx context.Context, channel *amqp.Channel, confirms <-chan amqp.Confirmation, original amqp.Delivery, exchange string, headers amqp.Table) error {
	message := amqp.Publishing{
		Headers:      headers,
		ContentType:  original.ContentType,
		DeliveryMode: amqp.Persistent,
		Timestamp:    time.Now().UTC(),
		Body:         original.Body,
	}
	routing := queueName
	if exchange == queueName+".dlq" {
		exchange = ""
		routing = queueName + ".dlq"
	}
	if err := channel.PublishWithContext(ctx, exchange, routing, true, false, message); err != nil {
		return fmt.Errorf("republish message: %w", err)
	}
	select {
	case confirmation, ok := <-confirms:
		if !ok || !confirmation.Ack {
			return errors.New("RabbitMQ did not confirm republished message")
		}
	case <-ctx.Done():
		return ctx.Err()
	case <-time.After(5 * time.Second):
		return errors.New("timed out waiting for RabbitMQ publisher confirmation")
	}
	return original.Ack(false)
}

func retryCount(headers amqp.Table) (int64, bool) {
	if headers == nil || headers["x-retry-count"] == nil {
		return 0, true
	}
	switch value := headers["x-retry-count"].(type) {
	case int8:
		return nonNegativeCount(int64(value))
	case int16:
		return nonNegativeCount(int64(value))
	case int32:
		return nonNegativeCount(int64(value))
	case int64:
		return nonNegativeCount(value)
	case int:
		return nonNegativeCount(int64(value))
	default:
		return 0, false
	}
}

func nonNegativeCount(value int64) (int64, bool) {
	if value < 0 {
		return 0, false
	}
	return value, true
}

func copyHeaders(headers amqp.Table) amqp.Table {
	copy := make(amqp.Table, len(headers)+1)
	for key, value := range headers {
		copy[key] = value
	}
	return copy
}
