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
    universal-ctags 

RUN python3 -m venv /opt/venv

ENV PATH "/opt/venv/bin:$PATH"

RUN python3 -m pip install pyyaml clang==16.0.1 colorama>=0.4.6 GitPython>=3.1.44 openlit==1.33.11 opentelemetry-api>=1.31.0 pexpect>=4.9.0 pika>=1.3.2 psycopg2-binary>=2.9.10 pydantic_core==2.27.2 pydantic==2.10.6 SQLAlchemy>=2.0.39 tree-sitter-java>=0.23.5 tree-sitter>=0.24.0  

WORKDIR /app

COPY reproducer/reproduce.py /app/reproduce.py
COPY reproducer/build_utils.py /app/build_utils.py
COPY reproducer/__init__.py /app/__init__.py
COPY patchagent /app/patchagent
COPY aixcc /app/aixcc

# RUN pip install --no-cache-dir -e .
COPY reproducer/scripts/main.sh /app/main.sh

RUN chmod +x /app/main.sh

ARG TASK_TYPE=reproducer
ENV TASK_TYPE=${TASK_TYPE}

ENTRYPOINT [ "/app/main.sh" ]