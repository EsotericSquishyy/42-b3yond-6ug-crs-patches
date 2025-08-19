.PHONY: all build clean test

# Default target
all: build

# Build the application
build:
	go build -o bin/crs-gateway ./cmd/crs-gateway

# Clean build artifacts
clean:
	rm -rf bin/

# Run tests
test:
	go test -v ./...

# Run tests with coverage
test-coverage:
	go test -v -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html

# Format code
fmt:
	go fmt ./...

# Run linter
lint:
	golangci-lint run

# Run the application
run: build
	./bin/crs-gateway

# Install dependencies
deps:
	go mod download
	go mod tidy

# Build docker image
docker-build:
	docker build -t crs-gateway .
