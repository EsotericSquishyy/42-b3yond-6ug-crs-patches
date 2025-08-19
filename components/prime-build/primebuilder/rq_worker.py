#!/usr/bin/env python3

import sys
import os
from redis import Redis
from rq import Worker, Queue

from .config import REDIS_URL, BUILD_QUEUE, WORKER_NAME_PREFIX
from .utils import generate_random_string
from loguru import logger

# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("worker_{time}.log", rotation="100 MB", level="DEBUG")


def main():
    """Run the RQ worker."""
    redis_conn = Redis.from_url(REDIS_URL)
    worker_name = f"{WORKER_NAME_PREFIX}_{generate_random_string(4)}"

    logger.info(f"Starting worker, connecting to {REDIS_URL}")
    logger.info(f"Worker name: {worker_name}")
    logger.info(f"Listening on queue: {BUILD_QUEUE}")

    worker = Worker([BUILD_QUEUE], connection=redis_conn, name=worker_name)
    worker.work()


if __name__ == "__main__":
    main()
