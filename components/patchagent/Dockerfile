FROM cruizba/ubuntu-dind:noble-latest

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install --no-install-recommends -y \
    clang \
    clang-16 \
    clangd \
    git \
    patch \
    python3 \
    python3-pip \
    python3.12-venv \
    universal-ctags \
    && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install --no-install-recommends -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv

ENV PATH "/opt/venv/bin:$PATH"

COPY testcases /testcases

WORKDIR /app

COPY patchagent /app/patchagent
COPY aixcc /app/aixcc
COPY patch_generator /app/patch_generator
COPY patch_submitter /app/patch_submitter
COPY pyproject.toml /app/pyproject.toml

RUN pip install --no-cache-dir -e .
COPY scripts/patch_generator.sh /app/patch_generator.sh
COPY scripts/patch_submitter.sh /app/patch_submitter.sh

ARG TASK_TYPE=generator
ENV TASK_TYPE=${TASK_TYPE}

ENTRYPOINT "/app/patch_${TASK_TYPE}.sh"
