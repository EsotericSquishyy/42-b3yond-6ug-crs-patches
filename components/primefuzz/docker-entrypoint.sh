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

if [ ! -z "$GHCR_SECRET_B64" ]; then
    echo "Setting up GHCR secret..."
    mkdir -p ~/.docker
    # Decode the base64 encoded secret and save it to the Docker config file
    echo $GHCR_SECRET_B64 | base64 -d > ~/.docker/config.json
    # Uncomment the following line if you want to use the decoded secret directly
    # docker login ghcr.io -u $CR_USERNAME --password-stdin < /root/.docker/config.json
fi

# login to ghcr
if [ ! -z "$CR_PAT" ] && [ ! -z "$CR_USERNAME" ]; then
    echo "Logging in to GitHub Container Registry..."
    echo $CR_PAT | docker login ghcr.io -u $CR_USERNAME --password-stdin
fi


if [ ! -z "$PULL_IMAGE_AIXCC" ] ; then
    echo "Pulling base-runner image... (preferred)"
    docker pull ghcr.io/aixcc-finals/base-runner:v1.2.1
    # docker tag ghcr.io/aixcc-finals/base-runner:v1.0.0 ghcr.io/aixcc-finals/base-runner:latest
fi

# Execute the main application
echo "Starting the main application..."
exec python run.py