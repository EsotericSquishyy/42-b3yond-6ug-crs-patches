FROM docker:24-dind

WORKDIR /app

# Install system dependencies
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
    python3-dev \
    patch

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY primebuilder/ ./primebuilder/
COPY entrypoint.sh .
COPY run.sh .

# Make scripts executable
RUN chmod +x entrypoint.sh run.sh

# Install Python dependencies
RUN pip install --no-cache-dir --break-system-packages -e .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CRS_MOUNT_PATH=/crs
ENV REPRODUCE_KEY=prime:reproduction
ENV OSS_FUZZ_LOCAL_PATH=/tmp/fuzz-tools-local

# Create a volume for data persistence
VOLUME /data

LABEL org.opencontainers.image.source=https://github.com/aixcc-finals/afc-crs-42-b3yond-6ug
LABEL org.opencontainers.image.description="Docker image for builder"
LABEL org.opencontainers.image.licenses=MIT

# Default entrypoint using the shell script
ENTRYPOINT ["/app/entrypoint.sh"]
