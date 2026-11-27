FROM golang:1.24-alpine AS build

WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/multiplayer ./cmd/multiplayer

FROM alpine:3.21
RUN apk add --no-cache ca-certificates && addgroup -S app && adduser -S -G app app
COPY --from=build /out/multiplayer /usr/local/bin/multiplayer
USER app
EXPOSE 8084
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD ["/usr/local/bin/multiplayer", "-health"]
ENTRYPOINT ["/usr/local/bin/multiplayer"]