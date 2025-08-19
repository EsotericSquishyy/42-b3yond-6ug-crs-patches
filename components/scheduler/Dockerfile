FROM golang:1.23-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o /scheduler ./cmd/scheduler

FROM alpine:latest
WORKDIR /app
COPY --from=builder /scheduler .
CMD ["./scheduler"]
