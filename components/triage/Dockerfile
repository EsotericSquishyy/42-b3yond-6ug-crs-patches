FROM cruizba/ubuntu-dind:noble-latest AS triage_runner

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
COPY ./parser ./parser
COPY ./infra ./infra
COPY ./utils ./utils
COPY ./dedup ./dedup
COPY ./task_handler.py ./task_handler.py
COPY ./requirements.txt ./requirements.txt

RUN npm install -g @modelcontextprotocol/server-filesystem
RUN npm install -g @openai/codex@0.1.2505140839
RUN npm install -g tree-sitter-cli

RUN git clone https://github.com/google/clusterfuzz.git
RUN git -C clusterfuzz checkout 40773ac07bda803aead9406bd6a83531048fa5a9

RUN pip3 install -r requirements.txt --break-system-packages

ENV PYTHONUNBUFFERED=1
ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

COPY ./entrypoint.sh ./entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]