#!/bin/sh
set -e

# Set default Redis host if not provided
# REDIS_HOST="${REDIS_HOST:-dev-redis-master}"

if [ -n "$REDIS_SENTINEL_HOSTS" ]; then
  for endpoint in ${REDIS_SENTINEL_HOSTS//,/ }; do
    host=${endpoint%%:*}
    port=${endpoint##*:}

    # quick liveness check
    if redis-cli -h "$host" -p "$port" PING &>/dev/null; then
      # ask this sentinel who the master is
      read REDIS_HOST REDIS_PORT < <(
        redis-cli -h "$host" -p "$port" \
          SENTINEL get-master-addr-by-name "$REDIS_MASTER"
      )
      break
    fi
  done
fi

if [ -z "$REDIS_HOST" ] ; then
  echo "ERROR: Couldn't determine Redis master from sentinels: $REDIS_SENTINEL_HOSTS" >&2
  # exit 1
fi

REDIS_KEY="${REDIS_KEY:-dind:hosts}"
# Get hostname
HOSTNAME=$(hostname)

echo "Starting DinD service with hostname: $HOSTNAME"

# Start Docker daemon
echo "Starting Docker daemon..."
dockerd -H tcp://0.0.0.0:2375 --tls=false --storage-driver=overlay2 &
DOCKER_PID=$!


export DOCKER_HOST=$HOSTNAME
# Wait for Docker to be ready
echo "Waiting for Docker to be ready..."
until docker info >/dev/null 2>&1; do
  sleep 1
done
echo "Docker daemon started"

# Create OSS_FUZZ_PATH directory if the env var exists
if [ -n "$OSS_FUZZ_PATH" ]; then
  echo "Creating directory: $OSS_FUZZ_PATH"
  mkdir -p "$OSS_FUZZ_PATH"
fi

# Pull required image
echo "Pulling base runner image..."
docker pull "${BASE_RUNNER_IMAGE:-ghcr.io/aixcc-finals/base-runner:v1.1.0}" || docker pull ghcr.io/aixcc-finals/base-runner:v1.0.0
# docker pull ghcr.io/aixcc-finals/base-runner:v1.1.0
echo "Image pulled successfully"

# Add host(s) to Redis set
if [ -n "$HEADLESS_SVC_NAME" ]; then
  # Resolve all addresses for the service name
  echo "Resolving addresses for $HEADLESS_SVC_NAME..."
  # addresses=$(getent hosts "$HEADLESS_SVC_NAME" | awk '{print $1}')
  
  # echo "Warning: Could not resolve any addresses for $HEADLESS_SVC_NAME"
  echo "Adding $HOSTNAME to $REDIS_KEY Redis set on $REDIS_HOST as fallback"
  redis-cli -h "$REDIS_HOST" SADD "$REDIS_KEY" "${HOSTNAME}.${HEADLESS_SVC_NAME}.${NAMESPACE}.svc.cluster.local"
else
  # Use hostname as before
  if [ -n "$DIND_SERIVCE_NAME" ]; then
    HOSTNAME="${DIND_SERIVCE_NAME}"
  fi
  # Add the hostname to the Redis set
  echo "Adding $HOSTNAME to $REDIS_KEY Redis set on $REDIS_HOST"
  redis-cli -h "$REDIS_HOST" SADD "$REDIS_KEY" "$HOSTNAME"
fi
echo "Hostname(s) added to Redis set"

# Keep the container running with the Docker daemon
echo "DinD setup complete. Waiting for Docker daemon to exit..."

echo "Starting metrics server..."

# Start the FastAPI server in the background
echo "Starting dind_load_api.py server..."
python3 /app/dind_load_api.py > /tmp/dind_load_api.log 2>&1 &
echo "FastAPI server started with PID $!"

wait $DOCKER_PID