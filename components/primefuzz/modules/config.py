from dataclasses import dataclass
from pathlib import Path
import os
import uuid
from dotenv import load_dotenv
from urllib.parse import urlparse, unquote


@dataclass
class Config:
    rabbitmq_host: str
    rabbitmq_port: int
    queue_name: str
    oss_fuzz_path: Path
    rabbitmq_user: str
    rabbitmq_password: str
    pg_connection_string: str
    pg_user: str
    pg_password: str
    metrics_interval: int = 60
    crs_mount_path: str = "/crs"
    enable_bug_profile: bool = False
    max_fuzzer_instances: int = 1
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    instance_id: str = ""
    directed_mode: bool = False
    directed_queue: str = ""
    otlp_endpoint: str = ""
    reproduction_prefix: str = ""
    enable_seed_archive: bool = False
    # nonsense additions
    additions_input_str: str = 'トゥットゥルー'
    redis_sentinel_hosts: str = ''
    redis_master: str = ''
    redis_password: str = ''

    @staticmethod
    def parse_database_url(url: str) -> tuple[str, str, str]:
        parsed = urlparse(url)

        # Decode username and password
        username = unquote(parsed.username) if parsed.username else ""
        password = unquote(parsed.password) if parsed.password else ""

        return (
            f"postgresql://{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}",
            username,
            password,
        )

    @classmethod
    def from_env(cls):
        load_dotenv()  # Load .env file if exists
        # Try DATABASE_URL first
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            try:
                pg_connection_string, pg_user, pg_password = cls.parse_database_url(
                    database_url
                )
            except Exception as e:
                raise ValueError(f"Invalid DATABASE_URL: {e}")
        else:
            # Fallback to individual env vars
            pg_connection_string = os.getenv(
                "PG_CONNECTION_STRING",
                "postgresql://b3yond-postgres-dev.postgres.database.azure.com:5432/b3yond-db-dev",
            )
            pg_user = os.getenv("PG_USER")
            pg_password = os.getenv("PG_PASSWORD")

        # Get instance ID from environment or generate a new one
        instance_id = os.getenv("INSTANCE_ID")
        if not instance_id:
            instance_id = "primefuzz-" + str(uuid.uuid4())
            os.environ["INSTANCE_ID"] = instance_id

        directed_mode = bool(os.getenv("DIRECTED_MODE", False))
        directed_queue = os.getenv(
            "DIRECT_QUEUE_NAME", "java_directed_fuzzing_queue")
        if directed_mode:
            os.environ["QUEUE_NAME"] = directed_queue

        # If OTEL_COLLECTOR_ENDPOINT is set, use it for OTEL_EXPORTER_OTLP_ENDPOINT
        collector_endpoint = os.getenv("OTEL_COLLECTOR_ENDPOINT")
        if collector_endpoint:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = collector_endpoint

        # Set REPRODUCE_KEY if it doesn't exist
        if not os.getenv("REPRODUCE_KEY"):
            os.environ["REPRODUCE_KEY"] = "prime:reproduction"

        return cls(
            rabbitmq_host=os.getenv("RABBITMQ_HOST", "localhost"),
            rabbitmq_port=int(os.getenv("RABBITMQ_PORT", "5672")),
            queue_name=os.getenv("QUEUE_NAME", "general_fuzzing_queue"),
            oss_fuzz_path=Path(os.getenv("OSS_FUZZ_PATH", "./fuzz-tooling")),
            rabbitmq_user=os.getenv("RABBITMQ_USER", "user"),
            rabbitmq_password=os.getenv("RABBITMQ_PASSWORD", "secret"),
            pg_connection_string=pg_connection_string,
            pg_user=pg_user,
            pg_password=pg_password,
            metrics_interval=int(os.getenv("METRICS_REFRESH_INTERVAL", "60")),
            crs_mount_path=os.getenv("CRS_MOUNT_PATH", "/crs"),
            max_fuzzer_instances=int(os.getenv("MAX_FUZZER_INSTANCES", "1")),
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=int(os.getenv("REDIS_DB", "0")),
            instance_id=instance_id,
            directed_mode=directed_mode,
            directed_queue=directed_queue,
            reproduction_prefix=os.getenv(
                "REPRODUCE_PREFIX", "prime:reproduction"),
            enable_seed_archive=bool(
                os.getenv("ENABLE_SEED_ARCHIVE", False)),
            otlp_endpoint=os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318"),
            redis_sentinel_hosts=os.getenv("REDIS_SENTINEL_HOSTS", ""),
            redis_master=os.getenv("REDIS_MASTER", ""),
            redis_password=os.getenv("REDIS_PASSWORD", None),
        )
