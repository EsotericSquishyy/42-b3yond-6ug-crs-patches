# Builder stage
FROM golang:1.23.4-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go install github.com/go-swagger/go-swagger/cmd/swagger@latest
RUN go build -o crs-gateway cmd/crs-gateway/main.go

# Final stage
FROM alpine:latest
COPY --from=builder /app/crs-gateway /usr/local/bin/crs-gateway
EXPOSE 8080
CMD ["crs-gateway"]