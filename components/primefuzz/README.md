# CRS Prime Fuzzer

A service that processes fuzzing tasks from RabbitMQ and executes OSS-Fuzz workflows.

## Prerequisites

- Python 3.11
- Docker
- kubectl (for local development with K8s)

## Installation

Clone the repository:

```
git clone <repository-url>
cd crs-prime-fuzz
```

## Configuration

Create a `.env` file:

```
# RabbitMQ Config
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=user
RABBITMQ_PASSWORD=secret
QUEUE_NAME=general_fuzzing_queue
DIRECT_QUEUE_NAME=java_directed_fuzzing_queue

# OSS-Fuzz Config 
OSS_FUZZ_PATH=./fuzz-tooling
CRS_MOUNT_PATH=/crs

# PostgreSQL Config
PG_CONNECTION_STRING=postgresql://fill-in
PG_USER=user
PG_PASSWORD=pass
POSTGRES_USER=user
POSTGRES_PASSWORD=pass
POSTGRES_DB=dbname
DATABASE_URL=postgresql://user:pass@host:5672/dbname

# Redis Config (for Java slicing)
REDIS_HOST=dev-redis-master
REDIS_PORT=6379

# GitHub Container Registry Config
CR_PAT=your_github_pat_here
CR_USERNAME=your_github_username

# Fuzzing Configuration
MAX_FUZZER_INSTANCES=1
# Only required by Java slicing
DIRECTED_MODE=True
PULL_IMAGE_AIXCC=1

# Metrics Collection
METRICS_REFRESH_INTERVAL=60
```

## Usage

### Local Development

1. Forward remote Kubernetes RabbitMQ port:

```
kubectl port-forward dev-rabbitmq-0 5672:5672
```

2. Run the service:

```
python run.py
```

### Docker Environment

The system consists of several interconnected services:

- **crs-java-slicer**: Service for Java code slicing
- **crs-prime-fuzz-javaslice**: Fuzzer with Java slicing capabilities
- **crs-prime-fuzz**: Standard fuzzer service
- **crs-prime-sentinel**: Monitoring service
- **dev-redis-master**: Redis for data exchange between services
- **dev-rabbitmq**: Message broker for task distribution
- **pgsql**: PostgreSQL database (optional, enabled with db_profile)

Run with docker-compose:

```
docker-compose up --build
```

To run only specific services:

```
docker-compose up crs-prime-fuzz dev-rabbitmq
```

Or to include the database (when using the profile):

```
docker-compose --profile db_profile up
```

### Resource Requirements

This section outlines the recommended compute resources for each service component. Resource allocation is based on workload characteristics and scaling factors.

**Variables:**
- **H**: Number of harness functions to be processed
- **S**: Number of sanitizer configurations in use

**Service Resources:**

| Service | CPU Requirements | Memory Requirements | Notes |
|---------|-----------------|-------------------|-------|
| crs-java-slicer | 4 cores | 8 GB | Fixed resource allocation |
| crs-prime-fuzz-javaslice | 2 × H cores | Scales with workload | Based on harness count |
| crs-prime-fuzz | 2 × H × 3 × S cores | Scales with workload | Based on both harness count and sanitizer configurations |
| crs-prime-sentinel | 1 core | 2 GB | Monitoring service with fixed allocation |

Proper resource allocation ensures optimal performance and prevents resource contention between services.

### Test on Remote Kubernetes Cluster

```
kubectl apply -f prime-k8s-deployment.yaml

# test with generate-task script
./generate-challenge-task.sh -t https://github.com/aixcc-finals/example-libpng.git -p libpng -c https://dev.crs.b3yond.org/ -o https://github.com/aixcc-finals/oss-fuzz-aixcc.git -v -r aixcc-exemplar-challenge-01 -b master

# please manually run the generated CURL script
```

FYI, check the service log.

```
kubectl exec <crs-prime-fuzz-pod-name> -- tail -f /tmp/prime_fuzz.log
```

An example of the logs:

```
> tail -f /tmp/prime_fuzz.log

2025-01-24 15:25:52,580 - workflow - INFO - Processing task
2025-01-24 15:25:52,580 - workflow - INFO - Processing task 18666e84-7840-4fb7-bd0b-a44510017dfa for project libpng
2025-01-24 15:25:55,557 - workflow - INFO - Using OSS-Fuzz path: /home/yun/code/aixcc/crs-prime-fuzz/18666e84-7840-4fb7-bd0b-a44510017dfa/fuzz-tooling
2025-01-24 15:25:55,625 - modules.fuzzing_runner - INFO - Building image for project: libpng
2025-01-24 15:26:05,826 - modules.fuzzing_runner - INFO - Building fuzzers: libpng
2025-01-24 15:26:15,796 - modules.fuzzing_runner - INFO - Checking build: libpng
2025-01-24 15:26:18,109 - modules.fuzzing_runner - INFO - Running fuzzer: libpng_read_fuzzer
```

## Integration with Helm Charts

Please refer to the [PR link](https://github.com/TBD-AIxCC/crs-k8s/pull/1/files).