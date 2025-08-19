#!/bin/sh

# Create log directory if it doesn't exist
mkdir -p /var/log

# Start Docker daemon with logging
dockerd --storage-driver=overlay2 > /var/log/dockerd_local.log 2>&1 &

# Wait for Docker to be ready
while ! docker info >/dev/null 2>&1; do
    echo "Waiting for Docker to start..."
    sleep 1
done

echo "Pulling base runner image..."
docker pull "${BASE_RUNNER_IMAGE:-ghcr.io/aixcc-finals/base-runner:v1.0.0}" || docker pull ghcr.io/aixcc-finals/base-runner:v1.0.0
docker pull ghcr.io/aixcc-finals/base-runner:v1.1.0

# Create OSS-Fuzz local path directory if it doesn't exist
echo "Creating OSS-Fuzz local path directory..."
mkdir -p "${OSS_FUZZ_LOCAL_PATH:-/tmp/fuzz-tools-local}"

# Execute the main application
echo "Starting the worker..."
exec python -m primebuilder.main run-worker