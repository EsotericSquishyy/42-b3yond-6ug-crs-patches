GOCMD = go
GOBUILD = $(GOCMD) build -buildvcs=false
GOCLEAN = $(GOCMD) clean
GOGET = $(GOCMD) get

BINARY_NAME = scheduler
BUILD_DIR = bin

.PHONY: all deps build clean scheduler

all: deps build

deps:
	$(GOGET) ./...

build: scheduler

scheduler:
	mkdir -p $(BUILD_DIR)
	$(GOBUILD) -o $(BUILD_DIR)/$(BINARY_NAME) ./cmd/scheduler

clean:
	$(GOCLEAN)
	rm -rf $(BUILD_DIR)