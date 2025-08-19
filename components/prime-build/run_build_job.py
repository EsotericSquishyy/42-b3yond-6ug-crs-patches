#!/usr/bin/env python3
"""
Run a build job and monitor its status.
e.g.
python run_build_job.py zookeeper /crs/backup/src/round-exhibition1-zookeeper 0195f1f6-117a-788f-aa72-a2365eade509 --share-oss-fuzz-path=/crs/backup/fuzz-tooling/fuzz-tooling
"""
import argparse
import time
import redis

from pathlib import Path
from loguru import logger
from rq import Queue
from rq.job import Job

from dotenv import load_dotenv
load_dotenv()
from primebuilder.config import REDIS_URL, BUILD_QUEUE
from primebuilder.main import build


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a build job and monitor its status")
    parser.add_argument(
        "project_name", help="Name of the OSS-Fuzz project to build")
    parser.add_argument("src_path", type=Path, help="Path to the source code")
    parser.add_argument("task_id", help="Task identifier")
    parser.add_argument("--skip-check", action="store_true",
                        help="Skip build check step")
    parser.add_argument("--share-oss-fuzz-path", type=Path,
                        help="Path to a shared OSS-Fuzz directory")

    return parser.parse_args()


def check_job_status(job_id):
    """Check the status of a job."""
    redis_conn = redis.from_url(REDIS_URL)
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        return job.get_status()
    except Exception as e:
        logger.error(f"Error fetching job status: {e}")
        return "error"


def main():
    args = parse_args()

    logger.info(f"Starting build job for project: {args.project_name}")
    logger.info(f"Source path: {args.src_path}")
    logger.info(f"Task ID: {args.task_id}")

    # Call the build function to create and queue the jobs
    job_id = build(
        args.project_name,
        args.src_path,
        args.task_id,
        args.skip_check,
        args.share_oss_fuzz_path
    )

    logger.info(f"Job queued successfully with ID: {job_id}")
    logger.info("Monitoring job status every 5 seconds...")

    # Monitor the job status
    start_time = time.time()
    done = False
    while not done:
        status = check_job_status(job_id)
        elapsed_time = int(time.time() - start_time)
        logger.info(
            f"Current job status: {status} (elapsed time: {elapsed_time}s)")

        if status in ["finished", "failed", "error"]:
            done = True
            logger.info(
                f"Job completed with status: {status} in {elapsed_time} seconds")
        else:
            time.sleep(5)  # Wait for 5 seconds before checking again


if __name__ == "__main__":
    main()
