FROM ghcr.io/aixcc-finals/afc-crs-42-b3yond-6ug/primebuilder:gold

# Install Python and dependencies
RUN apk add --no-cache \
    curl \
    file \
    git \
    jq \
    python3 \
    py3-pip \
    rsync \
    binutils \
    wget \
    gcc \
    python3-dev \
    musl-dev \
    patch \
    linux-headers

# Install YQ
ARG YQ_VERSION=4.43.1
ARG YQ_BINARY=yq_linux_amd64
RUN wget -q https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/${YQ_BINARY} -O /usr/bin/yq && \
    chmod +x /usr/bin/yq

# Set working directory
WORKDIR /app

# Copy requirements first for better cache usage
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy project files
COPY . .

# Copy entrypoint first and set permissions
COPY docker-entrypoint.sh .
RUN chmod +x /app/docker-entrypoint.sh && \
    dos2unix /app/docker-entrypoint.sh 2>/dev/null || true

LABEL org.opencontainers.image.source=https://github.com/aixcc-finals/afc-crs-42-b3yond-6ug
LABEL org.opencontainers.image.description="AIXCC CRS - fuzzing"

# Set environment variables
ENV RABBITMQ_HOST=dev-rabbitmq \
    RABBITMQ_PORT=5672 \
    QUEUE_NAME=general_fuzzing_queue \
    OSS_FUZZ_PATH=/app/fuzz-tooling \
    METRICS_REFRESH_INTERVAL=60 \
    CRS_MOUNT_PATH=/crs \
    DOCKER_TLS_CERTDIR="" \
    PYTHONUNBUFFERED=1 \
    MAX_FUZZER_INSTANCES=1 

# Use entrypoint script
ENTRYPOINT ["/app/docker-entrypoint.sh"]
