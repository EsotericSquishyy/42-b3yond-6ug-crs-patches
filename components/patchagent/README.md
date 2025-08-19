# PatchAgent

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-green.svg)](https://www.python.org/downloads/release/python-3120/)
[![Build Status](https://github.com/tbd-aixcc/PatchAgent/actions/workflows/ci.yaml/badge.svg)](https://github.com/tbd-aixcc/PatchAgent/actions/workflows/ci.yaml)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](docker-compose.yml)

An AI-powered automated vulnerability patching system that leverages Large Language Models (LLMs) to identify, understand, and fix security vulnerabilities in code.

## Overview

PatchAgent is designed to automatically fix vulnerabilities detected by various sanitizers (AddressSanitizer, LeakSanitizer, UndefinedBehaviorSanitizer, MemorySanitizer, and JazzerSanitizer). It uses advanced LLMs to understand and repair detected issues across multiple programming languages, currently supporting C/C++ and Java.

The agent works by:
1. Analyzing sanitizer reports to understand the vulnerability
2. Exploring the codebase to locate the root cause
3. Generating appropriate patches
4. Validating the patches against the proof-of-concept exploit
5. Ensuring the patch does not break existing functionality

## AI Integration

PatchAgent can work with multiple LLM providers including:
- OpenAI (GPT-4.1, GPT-4o, GPT-4o-mini)
- Anthropic (Claude 4 Opus, Claude 3.7/4 Sonnet, Claude 3.5 Haiku)

## Patch Modes

PatchAgent supports two main patching modes:

1. **Generic Mode**: The default mode that operates with multiple iterations and strategies for thorough vulnerability remediation.
2. **Fast Mode**: A streamlined mode designed to complete tasks in a single iteration, optimized for quick resolution.

The system starts in generic mode and can downgrade to fast mode if the task cannot be completed within a reasonable number of iterations.

## Architecture

### Project Structure

```
.
├── aixcc/                     # AIxCC integration layer
│   ├── builder/               # AIxCC builder extensions
│   │   ├── builder.py         # AIxCC builder implementation
│   │   ├── pool.py            # Builder pool management
│   │   └── utils.py           # Builder utilities
│   ├── db.py                  # Database models and connection
│   ├── env.py                 # Environment configuration
│   ├── logger.py              # Logging utilities
│   ├── main.py                # Main entry point
│   ├── mock.py                # Mock mode for testing
│   ├── telemetry.py           # Telemetry integration
│   └── utils.py               # Utility functions
├── patchagent/                # Core patching system
│   ├── agent/                 # LLM agent implementation
│   │   ├── clike/             # C/C++ language specific agents
│   │   │   ├── common.py      # Common C/C++ agent logic
│   │   │   ├── prompt.py      # C/C++ prompts
│   │   │   └── proxy/         # C/C++ tool proxies
│   │   ├── java/              # Java language specific agents
│   │   │   ├── common.py      # Common Java agent logic
│   │   │   ├── prompt.py      # Java prompts
│   │   │   └── proxy/         # Java tool proxies
│   │   ├── base.py            # Base agent class
│   │   └── generator.py       # Agent generation strategies
│   ├── builder/               # Build system abstraction
│   │   ├── builder.py         # Base builder class
│   │   └── ossfuzz.py         # OSS-Fuzz builder implementation
│   ├── lsp/                   # Language Server Protocol implementations
│   │   ├── clangd.py          # Clangd LSP for C/C++
│   │   ├── ctags.py           # Ctags for symbol location
│   │   ├── hybridc.py         # Hybrid C/C++ server
│   │   ├── java.py            # Java language server
│   │   └── language.py        # Abstract language server
│   ├── parser/                # Sanitizer report parsers
│   │   ├── address.py         # AddressSanitizer parser
│   │   ├── cwe.py             # CWE definitions and advice
│   │   ├── jazzer.py          # Jazzer parser for Java
│   │   ├── leak.py            # LeakSanitizer parser
│   │   ├── memory.py          # MemorySanitizer parser
│   │   ├── sanitizer.py       # Base sanitizer classes
│   │   └── undefined.py       # UndefinedBehaviorSanitizer parser
│   ├── context.py             # Agent interaction context
│   ├── lang.py                # Language enumerations
│   ├── task.py                # Patching task management
│   └── utils.py               # Utility functions
```

### Component Overview

#### PatchAgent Core (`patchagent/`)

The core vulnerability patching system includes:

- **Agent System**: Implements the LLM-powered agents for different languages
- **Builders**: Abstracts building and testing code across different environments
- **Language Servers**: Provides code analysis capabilities via LSP
- **Parsers**: Interprets sanitizer reports to identify vulnerability types
- **Task Management**: Coordinates the patching workflow

#### AIxCC Integration (`aixcc/`)

Integration layer for the AIxCC system:

- **Database Models**: Stores vulnerability and patch information
- **Message Queue**: Handles task distribution and processing
- **Telemetry**: Monitors and reports on system performance
- **Mock System**: Provides testing and development capabilities

## Environment Variables

### Mandatory Variables
| Variable | Description |
|----------|-------------|
| `OPENAI_BASE_URL` | OpenAI Base URL |
| `OPENAI_API_KEY` | OpenAI API Key |
| `AIXCC_DB_URL` | AIXCC DB Connection String |
| `AIXCC_RABBITMQ_URL` | AIXCC RabbitMQ Connection String |
| `AIXCC_RABBITMQ_PATCH_QUEUE` | AIXCC RabbitMQ Patch Queue |
| `AIXCC_RABBITMQ_PATCH_PRIORITY` | AIXCC RabbitMQ Patch Priority |
| `AIXCC_OTEL_EXPORTER_OTLP_ENDPOINT` | AIXCC OpenTelemetry Exporter OTLP Endpoint |
| `AIXCC_OTEL_EXPORTER_OTLP_HEADERS` | AIXCC OpenTelemetry Exporter OTLP Headers |
| `AIXCC_OTEL_EXPORTER_OTLP_PROTOCOL` | AIXCC OpenTelemetry Exporter OTLP Protocol |
| `AIXCC_MODEL` | AIXCC Model |

### Mock Mode Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `AIXCC_MOCK_MODE` | AIXCC Mock Mode | `full` |
| `AIXCC_MOCK_PATCH` | AIXCC Mock Patch | `all` |

## Docker Deployment

The project includes a complete Docker setup with:
- PostgreSQL database
- RabbitMQ message queue
- OpenTelemetry monitoring
- LiteLLM proxy for LLM API access

You can deploy the entire system using Docker Compose:

```bash
docker compose --profile patch up -d --build
```

## Examples

The repository includes example implementations for:
- ClamAV vulnerability patching
- Hamcrest Java library vulnerability patching

These examples demonstrate how to use PatchAgent with real-world projects.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
