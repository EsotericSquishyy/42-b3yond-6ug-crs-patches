FROM cruizba/ubuntu-dind:jammy-latest@sha256:8034042b686feabf2d7583e3aed654045f529309e813d5e9ac2d2095b9b7ab53

WORKDIR /app

# Install the required packages
RUN apt-get update && apt-get install -y \
    python3 python3-pip python-is-python3 \
    git \
    file \
    libpq-dev

RUN pip3 install --force-reinstall pika sqlalchemy psycopg2 docker watchdog psutil pyyaml redis tree-sitter==0.20.1 tree-sitter-languages==1.7.0 grpcio grpcio-tools openlit==1.33.21 opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp

# Test files accrording to crs-sarif
RUN mkdir /crs_sarif/tests -p
COPY tests /crs_sarif/tests

# Copy the source code
COPY src src

# Replace the entrypoint.sh with the one from the crs-directed
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh