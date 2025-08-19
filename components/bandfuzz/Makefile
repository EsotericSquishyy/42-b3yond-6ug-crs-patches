GOCMD = go
GOBUILD = $(GOCMD) build -buildvcs=false
GOCLEAN = $(GOCMD) clean
GOGET = $(GOCMD) get

BUILD_DIR = bin

.PHONY: all deps build clean b3fuzz mock

all: deps build

deps:
	$(GOGET) ./...

build: b3fuzz b3compile mock

b3fuzz:
	mkdir -p $(BUILD_DIR)
	$(GOBUILD) -o $(BUILD_DIR)/b3fuzz ./cmd/b3fuzz

b3compile:
	mkdir -p $(BUILD_DIR)
	$(GOBUILD) -o $(BUILD_DIR)/b3compile ./cmd/b3compile

mock:
	mkdir -p $(BUILD_DIR)
	$(GOBUILD) -o $(BUILD_DIR)/mock ./cmd/mock

clean:
	$(GOCLEAN)
	rm -rf $(BUILD_DIR)
