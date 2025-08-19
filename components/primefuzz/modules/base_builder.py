import time
import redis
import logging
from primebuilder.config import REDIS_URL, BUILD_QUEUE
from rq import Queue
from rq.job import Job


def check_job_status(job_id):
    """Check the status of a job."""
    logger = logging.getLogger(__name__)
    redis_conn = redis.from_url(REDIS_URL)
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        return job.get_status()
    except Exception as e:
        logger.error(f"Error fetching job status: {e}")
        return "error"


def wait_for_job(job_id, wait_time=600):
    # Monitor the job status
    start_time = time.time()
    logger = logging.getLogger(__name__)
    success = False
    done = False
    while not done:
        status = check_job_status(job_id)
        elapsed_time = int(time.time() - start_time)
        # Check if the job has timed out
        if elapsed_time >= wait_time:
            done = True
            logger.warning(
                f"Job timed out after {elapsed_time}s (wait_time: {wait_time}s)")
            return False

        logger.info(
            f"Current job status: {status} (elapsed time: {elapsed_time}s)")

        if status in ["finished", "success"]:
            done = True
            success = True
            logger.info(
                f"Job completed with status: {status} in {elapsed_time} seconds"
            )
        elif status in ["failed", "error"]:
            done = True
            logger.error(
                f"Job failed with status: {status} in {elapsed_time} seconds")
        else:
            time.sleep(5)  # Wait for 5 seconds before checking again

    return success
