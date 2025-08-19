FROM cruizba/ubuntu-dind:noble-latest AS triage_runner

ENV DEBIAN_FRONTEND=noninteractive
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
COPY . .
RUN pip3 install -r requirements.txt --break-system-packages
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["./entrypoint.sh"]
