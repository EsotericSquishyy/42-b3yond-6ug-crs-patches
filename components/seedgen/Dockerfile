# CallGraph runtime builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_callgraph
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY callgraph/runtime runtime
RUN cd runtime && cargo build --release

# CallGraph LLVM Pass builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_llvm_pass
WORKDIR /app
COPY callgraph/llvm /app/llvm
RUN cd llvm && ./build.sh

# Argus builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_argus
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY argus/ /app/argus/
RUN cd argus && cargo build --release

# Bandld builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_bandld
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY bandld/ /app/bandld/
RUN cd bandld && cargo build --release

# GetCov builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_getcov
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY getcov/ /app/getcov/
RUN cd getcov && cargo build --release

# SeedD builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_seedd
COPY --from=golang:1.22 /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}"
WORKDIR /app
COPY seedd/ /app/seedd/
RUN cd seedd && make


# Collect artifacts
# Use a minimal image to hold the artifacts
FROM cruizba/ubuntu-dind:noble-latest AS seedgen_runner

ENV DEBIAN_FRONTEND=noninteractive
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
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
    nodejs \
    && apt-get clean \
    && rm -rf /var/lib/{apt,dpkg,cache,log}

WORKDIR /app
RUN mkdir infra
COPY ./seedgen2 ./seedgen2
COPY ./infra ./infra
COPY ./utils ./utils
COPY ./task_handler.py ./task_handler.py
COPY ./requirements.txt ./requirements.txt

RUN mkdir -p infra/prebuilt
COPY --from=builder_callgraph /app/runtime/target/release/libcallgraph_rt.a ./infra/prebuilt/libcallgraph_rt.a
COPY --from=builder_llvm_pass /app/llvm/SeedMindCFPass.so ./infra/prebuilt/SeedMindCFPass.so
COPY --from=builder_argus /app/argus/target/release/argus ./infra/prebuilt/argus
COPY --from=builder_bandld /app/bandld/target/release/bandld ./infra/prebuilt/bandld
COPY --from=builder_getcov /app/getcov/target/release/getcov ./infra/prebuilt/getcov
COPY --from=builder_seedd /app/seedd/bin/seedd ./infra/prebuilt/seedd

RUN npm install -g @modelcontextprotocol/server-filesystem
RUN npm install -g @openai/codex@0.1.2504301751
RUN pip3 install -r requirements.txt --break-system-packages
RUN npm install -g tree-sitter-cli

ENV PYTHONUNBUFFERED=1

COPY ./entrypoint.sh ./entrypoint.sh
COPY ./treesitter_config.yaml ./treesitter_config.yaml

ENTRYPOINT ["./entrypoint.sh"]
