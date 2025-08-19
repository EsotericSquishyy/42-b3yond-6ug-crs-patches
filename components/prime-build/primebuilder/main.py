#!/usr/bin/env python3

import os
from pathlib import Path
import sys
from typing import Optional

import redis
import typer
from loguru import logger
from rq import Queue
from rq.job import Job

from .utils import generate_random_string
from .config import (REDIS_URL, BUILD_QUEUE,
                     ENABLE_COPY_ARTIFACT,
                     OSS_FUZZ_PATH,
                     JOB_RESULT_TTL,
                     WORKER_NAME_PREFIX,
                     WORKER_SLOT,
                     JOB_DATA_KEY_PREFIX)
from .worker import (
    fetch_source_code,
    build_image,
    build_fuzzers,
    build_image_and_fuzzers,
    check_build,
    copy_artifact,
    reproduce,
)

# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("/tmp/primebuild_worker_{time}.log",
           rotation="100 MB", level="DEBUG")

app = typer.Typer()


def setup_queue():
    """Set up and return an RQ queue."""
    redis_conn = redis.from_url(REDIS_URL)
    queue = Queue(BUILD_QUEUE, connection=redis_conn)
    return queue


def get_available_workers():
    """Get all workers that are not marked as occupied in Redis.

    Returns:
        list: List of available worker names
    """
    redis_conn = redis.from_url(REDIS_URL)
    # Get all registered workers from RQ
    all_workers = [worker.name for worker in Queue.all_workers(connection=redis_conn)
                   if worker.name.startswith(WORKER_NAME_PREFIX)]
    # Get all occupied workers from Redis set
    occupied_workers = redis_conn.smembers(WORKER_SLOT)
    # Convert bytes to strings if necessary
    occupied_workers = [w.decode() if isinstance(
        w, bytes) else w for w in occupied_workers]

    # Return workers that are not in the occupied set
    available_workers = [w for w in all_workers if w not in occupied_workers]
    logger.debug(f"Available workers: {available_workers}")
    return available_workers


def occupy_worker(worker_name: str):
    """Mark a worker as occupied by adding it to the Redis set.

    Args:
        worker_name: Name of the worker to mark as occupied

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        redis_conn = redis.from_url(REDIS_URL)
        redis_conn.sadd(WORKER_SLOT, worker_name)
        logger.info(f"Worker {worker_name} marked as occupied")
        return True
    except Exception as e:
        logger.error(f"Failed to occupy worker {worker_name}: {e}")
        return False


@app.command()
def build(
    project_name: str = typer.Argument(
        ..., help="Name of the OSS-Fuzz project to build"
    ),
    src_path: Path = typer.Argument(..., help="Path to the source code"),
    task_id: str = typer.Argument(..., help="Task identifier"),
    skip_check: bool = typer.Option(False, help="Skip build check step"),
    share_oss_fuzz_path: Optional[Path] = typer.Option(
        None, help="Path to a shared OSS-Fuzz directory to copy to OSS_FUZZ_PATH"
    ),
):
    """Build fuzzer for an OSS-Fuzz project using RQ job queue."""
    logger.info(f"Starting build process for project: {project_name}")

    # Validate that src_path exists
    if not src_path.exists():
        logger.error(f"Source path does not exist: {src_path}")
        raise typer.Exit(code=1)

    # Get absolute path
    src_path = src_path.absolute()

    # Create queue
    queue = setup_queue()
    logger.info(f"Connected to Redis at {REDIS_URL}")

    # Store initial job data directly in Redis
    redis_conn = queue.connection
    initial_data = {
        "project_name": project_name,
        "src_path": str(src_path),
        "task_id": task_id,
    }
    redis_conn.set(f"{JOB_DATA_KEY_PREFIX}:{task_id}", str(initial_data))

    # Enqueue jobs with dependencies
    # Step 1: Fetch source code
    if share_oss_fuzz_path:
        logger.info(
            f"Using shared OSS-Fuzz path: {share_oss_fuzz_path}")
    fetch_job = queue.enqueue(
        fetch_source_code,
        project_name,
        src_path,
        task_id,
        share_oss_fuzz_path,
        job_id=f"{task_id}_fetch",
        description=f"Fetch source code for {project_name}",
        result_ttl=JOB_RESULT_TTL,
        job_timeout=600,  # Increase timeout to 600 seconds
    )
    logger.info(f"Enqueued fetch job with ID: {fetch_job.id}")

    # Step 2: Build image
    # Step 3: Build fuzzers
    build_fuzzers_job = queue.enqueue(
        build_image_and_fuzzers,
        task_id,
        depends_on=fetch_job,
        job_id=f"{task_id}_build_fuzzers",
        description=f"Build fuzzers for {project_name}",
        result_ttl=JOB_RESULT_TTL,
        job_timeout=900,  # Increase timeout to 900 seconds
    )
    logger.info(f"Enqueued build_fuzzers job with ID: {build_fuzzers_job.id}")

    # Step 4: Check build (optional)
    last_job = build_fuzzers_job
    if not skip_check:
        check_build_job = queue.enqueue(
            check_build,
            task_id,
            depends_on=build_fuzzers_job,
            job_id=f"{task_id}_check_build",
            description=f"Check build for {project_name}",
            result_ttl=JOB_RESULT_TTL,
            job_timeout=600,  # Increase timeout to 600 seconds
        )
        logger.info(f"Enqueued check_build job with ID: {check_build_job.id}")
        last_job = check_build_job

    if ENABLE_COPY_ARTIFACT:
        # Step 5: Copy artifact (Skipped now)
        copy_job = queue.enqueue(
            copy_artifact,
            task_id,
            depends_on=last_job,
            job_id=f"{task_id}_copy_artifact",
            description=f"Copy artifacts for {project_name}",
            result_ttl=JOB_RESULT_TTL,
            job_timeout=600,  # Increase timeout to 600 seconds
        )
        logger.info(f"Enqueued copy_artifact job with ID: {copy_job.id}")

    logger.info(f"All jobs have been enqueued for project: {project_name}")
    logger.info(f"Final job ID: {last_job.id}")

    return last_job.id


@app.command()
def reproduce_crash(
    task_id: str = typer.Argument(..., help="Task identifier"),
    project: str = typer.Argument(..., help="Name of the project"),
    harness: str = typer.Argument(
        ..., help="The fuzzer harness to use for reproduction"
    ),
    testcase: Path = typer.Argument(..., help="Path to the test case file"),
    artifact_path: Optional[Path] = typer.Option(
        None, help="Path to artifact directory")
):
    """Reproduce a fuzzer crash using the specified harness and testcase."""
    logger.info(f"Starting reproduction process for project: {project}")

    # Validate that paths exist
    if not testcase.exists():
        logger.error(f"Testcase path does not exist: {testcase}")
        raise typer.Exit(code=1)

    # Set default artifact path if not provided
    if artifact_path is None:
        artifact_path = Path(OSS_FUZZ_PATH) / task_id / \
            "build" / "out" / project
        logger.info(f"Using default artifact path: {artifact_path}")
    else:
        # Ensure artifact_path is a Path object
        if not isinstance(artifact_path, Path):
            artifact_path = Path(artifact_path)

    # Get absolute paths
    artifact_path = artifact_path.absolute()
    testcase = testcase.absolute()

    # Create queue
    queue = setup_queue()
    logger.info(f"Connected to Redis at {REDIS_URL}")

    # Enqueue reproduction job
    reproduce_job = queue.enqueue(
        reproduce,
        task_id,
        str(artifact_path),
        project,
        harness,
        str(testcase),
        job_id=f"{task_id}_reproduce",
        description=f"Reproduce crash for {project} with harness {harness}",
        result_ttl=JOB_RESULT_TTL,  # Use configured TTL value
        job_timeout=300,  # Increase timeout to 600 seconds
    )
    logger.info(f"Enqueued reproduce job with ID: {reproduce_job.id}")
    logger.info(f"Reproduction job has been enqueued for project: {project}")
    return reproduce_job.id


@app.command()
def run_worker():
    """Run a worker to process jobs from the queue."""
    import subprocess

    logger.info(f"Starting worker for queue: {BUILD_QUEUE}")
    worker_name = f"{WORKER_NAME_PREFIX}_{generate_random_string(4)}"
    logger.info(f"Worker name: {worker_name}")
    subprocess.run(["rq", "worker", "--url", REDIS_URL,
                   "--name", worker_name, BUILD_QUEUE])


def main():
    app()


if __name__ == "__main__":
    main()
