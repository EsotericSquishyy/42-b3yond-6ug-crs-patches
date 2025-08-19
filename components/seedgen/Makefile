.PHONY: all build copy clean proto

# Define the image name
IMAGE_NAME = seedcoder-artifact-builder

# Default target
all: build copy

# Build the Docker image
build:
	docker build -t $(IMAGE_NAME) -f prebuilt.dockerfile .

# Create the prebuilt directory and copy artifacts from the container
copy:
	mkdir -p infra/prebuilt
	# Run a temporary container to copy files
	docker run --name temp-container $(IMAGE_NAME) /bin/true
	# Copy the artifacts from the container to the host
	docker cp temp-container:/prebuilt/. infra/prebuilt/
	# Remove the temporary container
	docker rm temp-container

# Clean up the prebuilt directory
clean:
	rm -rf infra/prebuilt

proto:
	protoc -I. --go_out=. seedd.proto
	protoc -I. --go-grpc_out=. seedd.proto
	python3 -m grpc_tools.protoc -I. --python_out=seedgen2/protobuf --grpc_python_out=seedgen2/protobuf --mypy_out=seedgen2/protobuf seedd.proto
	sed -i 's/import seedd_pb2 as seedd__pb2/from . import seedd_pb2 as seedd__pb2/' seedgen2/protobuf/seedd_pb2_grpc.py
