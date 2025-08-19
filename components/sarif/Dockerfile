FROM cruizba/ubuntu-dind:noble-latest

RUN apt-get update && apt-get install -y \
    python3 python3-pip python-is-python3 \
    git cmake file \
    libpq-dev \
    clang-18 llvm-18 libclang-18-dev 

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
&& apt-get update \
&& apt-get install -y nodejs \
&& apt-get clean -y

RUN npm install -g @modelcontextprotocol/server-filesystem

RUN pip3 install --break-system-packages pika sqlalchemy psycopg2 \
    sarif-tools \
    tree-sitter tree-sitter-language-pack

RUN pip3 install --break-system-packages --ignore-installed \
    mcp-agent anthropic>=0.49.0 uv mcp-server-fetch mcp-server-tree-sitter openai>=1.74.1

RUN pip3 install --break-system-packages \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-distro \
    opentelemetry-exporter-otlp \
    openlit

COPY src /app

# build code_injector
WORKDIR /app/code_injector
RUN mkdir -p build
WORKDIR /app/code_injector/build
ENV CXX=clang++-18
RUN cmake .. && make

WORKDIR /app

COPY crs-prime-sarif-evaluator /app/crs-prime-sarif-evaluator


# COPY tests/exemplar /tests/

CMD ["python3", "app.py", "--debug"]