import os
from pathlib import Path

from aixcc.env import getenv_or_raise

OPENAI_BASE_URL: str = getenv_or_raise("OPENAI_BASE_URL")

OPENAI_API_KEY: str = getenv_or_raise("OPENAI_API_KEY")

RABBITMQ_URL: str = getenv_or_raise("AIXCC_RABBITMQ_URL")

RABBITMQ_PATCH_QUEUE: str = getenv_or_raise("AIXCC_RABBITMQ_PATCH_QUEUE")

RABBITMQ_PATCH_PRIORITY: int = int(getenv_or_raise("AIXCC_RABBITMQ_PATCH_PRIORITY"))

OTEL_EXPORTER_OTLP_ENDPOINT: str = getenv_or_raise("AIXCC_OTEL_EXPORTER_OTLP_ENDPOINT")

OTEL_EXPORTER_OTLP_HEADERS: str = getenv_or_raise("AIXCC_OTEL_EXPORTER_OTLP_HEADERS")

OTEL_EXPORTER_OTLP_PROTOCOL: str = getenv_or_raise("AIXCC_OTEL_EXPORTER_OTLP_PROTOCOL")

MODEL: str = getenv_or_raise("AIXCC_MODEL")

MOCK_MODE: str = os.getenv("AIXCC_MOCK_MODE", "full")

MOCK_MODEL: str = os.getenv("AIXCC_MOCK_MODEL", "all")

WORKSPACE: Path = Path("/patch_generator")
