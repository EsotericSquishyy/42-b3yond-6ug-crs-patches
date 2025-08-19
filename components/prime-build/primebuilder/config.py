import os
from pathlib import Path

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Queue names
BUILD_QUEUE = "public_build_queue"

# Worker name prefix
WORKER_NAME_PREFIX = os.getenv("WORKER_NAME_PREFIX", "primebuilder")

# OSS-Fuzz configuration
OSS_FUZZ_PATH = Path(os.getenv("OSS_FUZZ_PATH", "/data/fuzz-tools"))
OSS_FUZZ_LOCAL_PATH = Path(os.getenv("OSS_FUZZ_LOCAL_PATH", "/tmp/fuzz-tools-local"))
CRS_MOUNT_PATH = Path(os.getenv("CRS_MOUNT_PATH", "/crs"))

# Docker settings
DOCKER_PLATFORM = "linux/amd64"
ENABLE_COPY_ARTIFACT = os.getenv(
    "ENABLE_COPY_ARTIFACT", "false").lower() == "true"
BASE_RUNNER_IMAGE = os.getenv(
    "BASE_RUNNER_IMAGE", "ghcr.io/aixcc-finals/base-runner:v1.1.0"
)
BASE_RUNNER_IMAGE = "ghcr.io/aixcc-finals/base-runner:v1.1.0"

# Redis key prefixes
JOB_DATA_KEY_PREFIX = os.getenv("JOB_DATA_KEY_PREFIX", "prime:job_data")
# Redis work slot
WORKER_SLOT = os.getenv("WORKER_SLOT", "prime:worker_slot")
# Redis result TTL
JOB_RESULT_TTL = int(os.getenv("JOB_RESULT_TTL", 21600))  # 6 hour

REPRODUCTION_KEY = os.getenv("REPRODUCE_KEY", "prime:reproduction")
