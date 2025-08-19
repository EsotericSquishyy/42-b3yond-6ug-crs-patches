FROM golang:1.23-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o /b3compile ./cmd/b3compile

FROM cruizba/ubuntu-dind:noble-latest
RUN apt-get update && apt-get -y install \
    7zip \
    autoconf \
    automake \
    autotools-dev \
    bash \
    binutils \
    bsdextrautils \
    build-essential \
    ca-certificates \
    curl \
    file \
    git \
    git-lfs \
    gnupg2 \
    gzip \
    jq \
    libcap2 \
    ltrace \
    make \
    openssl \
    patch \
    perl-base \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-venv \
    python3-wheel \
    python-is-python3 \
    rsync \
    software-properties-common \
    strace \
    tar \
    tzdata \
    unzip \
    vim \
    wget \
    xz-utils \
    zip \
    && apt-get clean \
    && rm -rf /var/lib/{apt,dpkg,cache,log}
WORKDIR /app
COPY --from=builder /b3compile .
COPY libcmin.a /libcmin.a
ENTRYPOINT ["/bin/bash", "-c"]
ENV SERVICE_NAME="BandBuilding"
CMD ["start-docker.sh && ./b3compile"]
