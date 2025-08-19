FROM mcr.microsoft.com/devcontainers/python:3.12

# Install Node.js (needed for npx commands)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get update \
    && apt-get install -y nodejs \
    && apt-get clean -y

# Install global npm packages
RUN npm install -g @modelcontextprotocol/server-filesystem
RUN npm install -g @openai/codex@0.1.2505140839
# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install mcp-agent anthropic uv mcp-server-fetch mcp-server-tree-sitter \
    && npm install -g tree-sitter-cli

WORKDIR /workspaces/crs-triage

