import os
import redis
from redis.sentinel import Sentinel
import logging
import shutil
import time
import tempfile
import threading

from pathlib import Path

from utils.thread import ExceptionThread
from utils.misc import get_file_sha256, safe_extract_tar

class SeedSyncer:
    def __init__(self, task_id, harness, output_dir, interval=600):
        """
        Initialize Redis connection and background sync task.
        
        Args:
            task_id (str): Task identifier.
            harness (str): Harness name.
            output_dir (str): Output directory for syncing seeds.
            interval (int, optional): Interval in seconds to check Redis. Defaults to 10 mins.
            redis_url (str, optional): Redis connection URL. Defaults to REDIS_URL env var or localhost.
        """
        self.task_id = task_id
        self.harness = harness
        self.redis_sentinel_hosts = os.environ.get("REDIS_SENTINEL_HOSTS", "crs-redis-sentinel:26379")
        self.redis_master = os.environ.get("REDIS_MASTER", "mymaster")
        self.redis_password = os.environ.get("REDIS_PASSWORD", None)
        
        # Parse sentinel hosts from string to list of tuples
        sentinel_hosts = redis_sentinel_hosts = [(h, int(p)) for h, p in (item.split(":") for item in self.redis_sentinel_hosts.split(","))]
        
        # Initialize Sentinel
        self.sentinel = Sentinel(sentinel_hosts, socket_timeout=5.0, password=self.redis_password)
        
        # Get master for the specified master name
        self.client = self.sentinel.master_for(
            self.redis_master,
            socket_timeout=5.0,
            password=self.redis_password,
            db=0,
            decode_responses=True
        )
        self.output_dir = output_dir
        self.interval = interval
        self.running = False
        self.thread = None
        self.seed_hash = None
        self.last_id = 0
        self.stop_event = threading.Event()

    @property
    def get_queue_dir(self):
        """
        Returns the queue directory for the given harness.
        
        Returns:
            str: The queue directory path.
        """
        return Path(self.output_dir) / f"{self.harness}_afl_address_out/sync_dir/queue"

    def get_cmin_path(self):
        """
        Fetches the latest seeds path for the given task and harness.
        
        Returns:
            str: The path to the latest seeds, or None if not found.
        """
        return self.client.get(f"cmin:{self.task_id}:{self.harness}")

    def sync_seeds(self, path):
        """
        Syncs the seeds from the given path.
        
        Args:
            path (str): Path to the cmin file.
        """
        if path is None:
            logging.warning(f"No path found for task: {self.task_id}, harness: {self.harness}")
            return
        
        new_hash = get_file_sha256(path)
        if new_hash == self.seed_hash:
            logging.info(f"Seeds already synced for task: {self.task_id}, harness: {self.harness}")
            return
        
        logging.info(f"Syncing seeds from: {path}")
        sync_queue_dir = self.get_queue_dir
        
        with tempfile.TemporaryDirectory() as tmpdir:
            safe_extract_tar(path, tmpdir)
            for file in sorted(Path(tmpdir).iterdir()):
                new_filename = f"id:{self.last_id:06d}"
                # ! queue_dir should be created at start, but sometimes the directory does not exist when copy?
                sync_queue_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(file), sync_queue_dir / new_filename)
                self.last_id += 1
    
        self.seed_hash = new_hash
        logging.info(f"Seeds synced for task: {self.task_id}, harness: {self.harness}, hash: {self.seed_hash}")

    def _sync_loop(self):
        """ Background loop to periodically fetch the cmin path. """
        while self.running:
            try:
                path = self.get_cmin_path()
                logging.info(f"Task: {self.task_id}, Harness: {self.harness}, Path: {path}")
                self.sync_seeds(path)
            except Exception as e:
                logging.error(f"Error: {e}")
            self.stop_event.wait(timeout=self.interval)

    def start(self):
        """ Start the background sync process with exception handling. """
        if not self.running:
            self.running = True
            self.get_queue_dir.mkdir(parents=True, exist_ok=True)
            self.thread = ExceptionThread(target=self._sync_loop, daemon=True)
            self.thread.start()
            logging.info("Background sync started.")

    def stop(self):
        """ Stop the background sync process. """
        if self.running:
            self.running = False
            self.stop_event.set()
            if self.thread:
                self.thread.join()
            self.close()
            logging.info("Background sync stopped.")

    def close(self):
        """ Close the Redis connection. """
        self.client.close()
