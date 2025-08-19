GOCMD = go
GOBUILD = $(GOCMD) build -buildvcs=false
GOCLEAN = $(GOCMD) clean
GOGET = $(GOCMD) get

BINARY_NAME = seedd
BUILD_DIR = bin

all: deps build

deps:
	$(GOGET) ./...

build: seedd

seedd:
	CGO_ENABLED=0 $(GOBUILD) -o $(BUILD_DIR)/$(BINARY_NAME) ./cmd/seedd

clean:
	$(GOCLEAN)
	rm -rf $(BUILD_DIR)