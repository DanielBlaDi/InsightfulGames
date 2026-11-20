package messaging

import (
	"testing"

	amqp "github.com/rabbitmq/amqp091-go"
)

func TestRetryCount(t *testing.T) {
	tests := []struct {
		name    string
		headers amqp.Table
		want    int64
		valid   bool
	}{
		{name: "missing", headers: nil, want: 0, valid: true},
		{name: "int32", headers: amqp.Table{"x-retry-count": int32(3)}, want: 3, valid: true},
		{name: "negative", headers: amqp.Table{"x-retry-count": int32(-1)}, valid: false},
		{name: "wrong type", headers: amqp.Table{"x-retry-count": "3"}, valid: false},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got, valid := retryCount(test.headers)
			if got != test.want || valid != test.valid {
				t.Fatalf("retryCount() = (%d, %t), want (%d, %t)", got, valid, test.want, test.valid)
			}
		})
	}
}
