FROM cruizba/ubuntu-dind:focal-latest@sha256:8273ea70f374fe39b6f376698c64627225276049c2f9574ae968ade3d2856409

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 python3-pip python-is-python3 \
    git \
    libpq-dev \
    wget \
    lsb-release \
    software-properties-common \
    gnupg

# Add LLVM repository
RUN wget -O - https://apt.llvm.org/llvm-snapshot.gpg.key | apt-key add - && \
    add-apt-repository "deb http://apt.llvm.org/focal/ llvm-toolchain-focal-14 main"

# Install LLVM 14 packages
RUN apt-get update && apt-get install -y \
    llvm-14 \
    llvm-14-dev \
    llvm-14-tools \
    clang-14

# Set environment variables to use LLVM 14 tools without version suffix
ENV PATH="/usr/lib/llvm-14/bin:${PATH}"
ENV LLVM_CONFIG=/usr/bin/llvm-config-14

RUN pip3 install pika sqlalchemy psycopg2 docker grpcio grpcio-tools openlit opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp

WORKDIR /app

COPY base-builder.tar.gz base-builder.tar.gz
RUN gunzip base-builder.tar.gz

COPY oss-fuzz-aixcc oss-fuzz-aixcc
COPY slice.py slice.py

# Test files accrording to crs-sarif
RUN mkdir /crs_sarif/tests -p
COPY tests /crs_sarif/tests

COPY src src

# Replace the entrypoint.sh with the one from the crs-slice
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# At this point, we need to run the container and load the base-builder image, later commit the container to create the crs-slice image