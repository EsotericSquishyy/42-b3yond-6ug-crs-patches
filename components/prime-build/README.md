# Prime Builder

A job queue system for building OSS-Fuzz projects using Redis Queue (RQ).

## Installation

```bash
pip install -e .
```

## Requirements

- Python 3.11+
- Redis server
- Docker

## Environment Variables

Set the following environment variables before running:

- `REDIS_HOST`: Redis host (default: localhost)
- `REDIS_PORT`: Redis port (default: 6379)
- `OSS_FUZZ_PATH`: Path to OSS-Fuzz code
- `CRS_MOUNT_PATH`: Path to CRS mount (default: /crs)

## Usage

### Start a dind service

```
docker run --add-host=dev-redis-master=192.168.50.17 --name dind-prime --privileged --rm -e DIND_SERIVCE_NAME=gpu.fuzzingbrain.com -p 2375:2375 -v /crs:/crs ghcr.io/aixcc-finals/afc-crs-42-b3yond-6ug/dind:prime
```

### Start a worker

```bash
./run.sh run-worker
```

### Submit a build job

```bash
./run.sh build xz /home/yun/code/targets/xz $(uuidgen)
```

### Skip build check

```bash
python main.py build project_name /path/to/source/code task_identifier --skip-check
```

## Docker Usage

### Build the Docker image

```bash
docker build -t ghcr.io/tbd-aixcc/prime-build/builder .
```

### Run the Docker container

```bash
docker run --rm --privileged --add-host=dev-redis-master=192.168.50.17 -v $(pwd)/data:/data -v /crs:/crs --env-file .env ghcr.io/tbd-aixcc/prime-build/builder
```

### Using Docker Compose

To run both the DinD service and Prime Builder together:

```bash
docker-compose up
```
