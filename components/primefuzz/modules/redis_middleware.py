import json
import redis
import logging
from redis.sentinel import Sentinel
from typing import Optional
from modules.config import Config

logger = logging.getLogger(__name__)


class RedisMiddleware:
    def __init__(self):
        self.config = Config.from_env()
        self.sentinel = None

        # Initialize with Sentinel if sentinel hosts and master are provided
        if self.config.redis_sentinel_hosts and self.config.redis_master:
            try:
                # Parse sentinel hosts into list of (host, port) tuples
                sentinel_hosts = []
                for host_port in self.config.redis_sentinel_hosts.split(","):
                    host, port = host_port.strip().split(":")
                    sentinel_hosts.append((host, int(port)))

                self.init_redis(sentinel_hosts=sentinel_hosts,
                                master_name=self.config.redis_master,
                                password=self.config.redis_password,)
                logger.debug(
                    f"Initialized Redis with Sentinel, master: {self.config.redis_master}")
            except Exception as e:
                logger.error(
                    f"Failed to initialize Redis with Sentinel: {str(e)}")
        # Fallback to direct connection already set above
        else:
            self.redis_client = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
                decode_responses=True,
            )

        # Continue with the rest of initialization
        self.tasks_key_prefix = "primefuzz:task:"
        self.slice_task_key_prefix = "javaslice:task:"
        self.slice_task_result_suffix = ":result"
        self.public_backup_key_prefix = "public:build:"
        self.tasks_status_key = f"{self.tasks_key_prefix}task_status"
        self.task_metrics_key_prefix = f"{self.tasks_key_prefix}metrics:"
        self.task_metadata_key_prefix = f"global:task_metadata:"
        self.docker_hosts_key = f"dind:hosts"
        self.reproduction_prefix = self.config.reproduction_prefix
        self.task_metrics_expiration = 15 * 60  # 15 min
        self.slice_task_expiration = 24 * 60 * 60  # 24 hours
        self.prime_task_expiration = 48 * 60 * 60  # 48 hours

    def init_redis(self, sentinel_hosts, master_name, password=None, db=0):
        """
        Initialize Redis client using Sentinel

        Args:
            sentinel_hosts (list): List of (host, port) tuples for Sentinel nodes
            master_name (str): Name of the master to monitor
            password (str, optional): Redis password
            db (int, optional): Redis database number
        """

        # Initialize Sentinel
        self.sentinel = Sentinel(
            sentinel_hosts, socket_timeout=5.0, password=password)

        try:
            # Get master for the specified master name
            self.redis_client = self.sentinel.master_for(
                master_name,
                socket_timeout=5.0,
                password=password,
                db=db,
                decode_responses=True
            )

            if self.redis_client.ping():
                logger.debug(
                    f"Redis client initialized via Sentinel for master '{master_name}'")
        except redis.exceptions.ConnectionError as e:
            logger.warning(f"Redis Sentinel connection failed: {e}")

    async def set_task_metadata(self, task_id: str, metadata: str) -> bool:
        """
        Set task metadata in Redis

        Args:
            task_id: Task identifier
            metadata: Metadata value to store
        Returns:
            bool: Success status
        """
        try:
            metadata_key = f"{self.task_metadata_key_prefix}{task_id}"
            self.redis_client.set(metadata_key, metadata)
            # Set expiration to match payload expiration
            self.redis_client.expire(metadata_key, self.prime_task_expiration)
            logger.info(f"Set metadata for task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set task metadata: {str(e)}")
            return False

    def get_task_metadata(self, task_id: str) -> Optional[str]:
        """
        Get task metadata from Redis

        Args:
            task_id: Task identifier
        Returns:
            Optional[str]: Task metadata or None if not found
        """
        try:
            metadata_key = f"{self.task_metadata_key_prefix}{task_id}"
            metadata = self.redis_client.get(metadata_key)
            return metadata
        except Exception as e:
            logger.error(f"Failed to get task metadata: {str(e)}")
            return None

    def get_reproduce_result(
        self,
        task_id: str,
        harness: str,
        testcase_name: str,
        redis_key_prefix: str = "prime:reproduction",
    ) -> Optional[dict]:
        """
        Retrieve reproduction result from Redis

        Args:
            redis_key_prefix: Prefix used for reproduction keys
            task_id: Task identifier
            harness: Harness name
            testcase_name: Name of the testcase file
        Returns:
            Optional[str]: Reproduction result data or None if not found
        """
        try:
            redis_key_prefix = redis_key_prefix or self.reproduction_prefix
            repro_key = f"{redis_key_prefix}:{task_id}:{harness}:{testcase_name}"
            result = json.loads(self.redis_client.get(repro_key))
            return result
        except Exception as e:
            logger.error(f"Failed to get reproduction result: {str(e)}")
            return {}

    def get_basebuilder_job_data(self, task_id: str):
        job_data_prefix = "prime:job_data"
        job_data_key = f"{job_data_prefix}:{task_id}"
        try:
            result = self.redis_client.get(job_data_key)
            return result
        except Exception as e:
            logger.error(f"Failed to get job data: {str(e)}")
            return None

    def get_slice_task_result(self, task_id: str) -> Optional[str]:
        """
        Retrieve slice task result from Redis

        Args:
            task_id: Task identifier
        Returns:
            Optional[str]: Task result or None if not found
        """
        try:
            result_key = (
                f"{self.slice_task_key_prefix}{task_id}{self.slice_task_result_suffix}"
            )
            result = self.redis_client.get(result_key)
            return result
        except Exception as e:
            logger.error(f"Failed to get slice task result: {str(e)}")
            return None

    async def record_public_backup(self, task_id: str, payload: dict) -> bool:
        """
        Record or remove public backup
        Returns True if operation was successful
        """
        try:
            public_backup_key = f"{self.public_backup_key_prefix}{task_id}"
            self.redis_client.set(public_backup_key, json.dumps(payload))

            # Set expiration similar to other tasks
            self.redis_client.expire(
                public_backup_key, self.slice_task_expiration)

            logger.info(f"Recorded public backup for task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Redis operation failed: {str(e)}")
            return False

    async def record_slice_task(self, task_id: str, payload: str) -> bool:
        """
        Record or remove slice task
        Returns True if operation was successful
        """
        try:
            slice_task_key = f"{self.slice_task_key_prefix}{task_id}"
            # Store the payload as value for the slice task key
            self.redis_client.set(slice_task_key, payload)

            # Set expiration similar to other tasks (4 hours)
            self.redis_client.expire(
                slice_task_key, self.slice_task_expiration)

            logger.info(f"Recorded slice task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Redis operation failed: {str(e)}")
            return False

    async def record_task(self, task_id: str, task_type: str) -> bool:
        """
        Record or remove task based on task type
        Returns True if operation was successful
        """
        try:
            if task_type in ["delta", "full"]:
                self.redis_client.sadd(self.tasks_status_key, task_id)
                logger.info(f"Recorded task {task_id} of type {task_type}")
                return True
            elif task_type == "cancel":
                self.redis_client.srem(self.tasks_status_key, task_id)
                logger.info(f"Removed task {task_id} from active tasks")
                return True
            return False
        except Exception as e:
            logger.error(f"Redis operation failed: {str(e)}")
            return False

    async def record_task_data(self, payload: dict) -> bool:
        """
        Store complete message payload in Redis

        Args:
            payload: Decoded message payload as dictionary
        Returns:
            bool: Success status
        """
        try:
            task_id = payload.get("task_id")
            if not task_id:
                logger.error("Missing task_id in payload")
                return False

            task_type = payload.get("task_type")
            # record slice task
            # if task_type == "delta":
            #     self.record_slice_task(task_id, json.dumps(payload))

            # Convert all values to strings for Redis storage
            redis_payload = {
                k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                for k, v in payload.items()
            }

            # Store in Redis hash
            hash_key = f"{self.tasks_key_prefix}{task_id}:payload"
            self.redis_client.hmset(hash_key, redis_payload)

            # Set expiration (e.g., 2 days)
            self.redis_client.expire(hash_key, self.prime_task_expiration)

            logger.info(f"Stored complete payload for task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to store message payload: {str(e)}")
            return False

    async def remove_record_task(self, task_id: str) -> bool:
        """
        Remove task from active set and delete its payload data

        Args:
            task_id: Task identifier to remove
        Returns:
            bool: True if operation was successful
        """
        try:
            # Remove from active set
            self.redis_client.srem(self.tasks_status_key, task_id)

            # Remove payload data
            hash_key = f"{self.tasks_key_prefix}{task_id}:payload"
            self.redis_client.delete(hash_key)

            logger.info(f"Removed all task payloads for task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove task records: {str(e)}")
            return False

    def get_task_payload(self, task_id: str) -> dict:
        """
        Retrieve complete task payload

        Args:
            task_id: Task identifier
        Returns:
            dict: Complete task payload or empty dict if not found
        """
        try:
            hash_key = f"{self.tasks_key_prefix}{task_id}:payload"
            data = self.redis_client.hgetall(hash_key)

            if not data:
                return {}

            # Convert stored JSON strings back to Python objects
            return {
                k: json.loads(v) if v.startswith(
                    "{") or v.startswith("[") else v
                for k, v in data.items()
            }

        except Exception as e:
            logger.error(f"Failed to retrieve task payload: {str(e)}")
            return {}

    def is_task_active(self, task_id: str) -> bool:
        """Check if task is in the active set"""
        return self.redis_client.sismember(self.tasks_status_key, task_id)

    def get_active_tasks(self) -> set:
        """Get all active tasks"""
        return self.redis_client.smembers(self.tasks_status_key)

    async def set_global_task_status(self, task_id: str, status: str) -> bool:
        """
        Set task status in Redis

        Args:
            task_id: Task identifier
            status: Status value ('processing' or 'canceled')
        Returns:
            bool: Success status
        """
        if status not in ["processing", "canceled"]:
            logger.error(f"Invalid task status: {status}")
            return False

        try:
            status_key = f"global:task_status:{task_id}"
            self.redis_client.set(status_key, status)
            # Set expiration to match payload expiration (24 hours)
            self.redis_client.expire(status_key, 60 * 60 * 24)
            logger.info(f"Set status '{status}' for task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set task status: {str(e)}")
            return False

    def remove_global_task_status(self, task_id: str) -> bool:
        """
        Remove task status from Redis

        Args:
            task_id: Task identifier
        Returns:
            bool: Success status
        """
        try:
            status_key = f"global:task_status:{task_id}"
            self.redis_client.delete(status_key)
            logger.info(f"Removed status for task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove task status: {str(e)}")
            return False

    def get_global_task_status(self, task_id: str) -> Optional[str]:
        """
        Get task status from Redis

        Args:
            task_id: Task identifier
        Returns:
            Optional[str]: Task status ('processing' or 'canceled') or None if not found
        """
        try:
            status_key = f"global:task_status:{task_id}"
            status = self.redis_client.get(status_key)
            return status if status else ""
        except Exception as e:
            logger.error(f"Failed to get task status: {str(e)}")
            return ""

    async def append_task_metrics(self, task_id: str, metrics: dict) -> bool:
        """
        Append metrics record to the task's metrics list in Redis

        Args:
            task_id: Task identifier
            metrics: Dictionary containing metrics data
        Returns:
            bool: Success status
        """
        try:
            metrics_key = f"{self.task_metrics_key_prefix}{task_id}"

            # Convert metrics dict to JSON string
            metrics_json = json.dumps(metrics)

            # Use RPUSH to append to list
            self.redis_client.rpush(metrics_key, metrics_json)

            # Set/reset expiration
            self.redis_client.expire(metrics_key, self.task_metrics_expiration)

            logger.debug(f"Appended metrics for task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to append task metrics: {str(e)}")
            return False

    def get_latest_task_metrics(self, task_id: str) -> Optional[dict]:
        """
        Get the most recent metrics record for a task

        Args:
            task_id: Task identifier
        Returns:
            Optional[dict]: Latest metrics dictionary or None if not found
        """
        try:
            metrics_key = f"{self.task_metrics_key_prefix}{task_id}"

            # Get last element of list (-1 index)
            latest_json = self.redis_client.lindex(metrics_key, -1)

            if not latest_json:
                return None

            # Parse JSON string back to dict
            return json.loads(latest_json)

        except Exception as e:
            logger.error(f"Failed to get latest task metrics: {str(e)}")
            return None

    async def increment_workflow_retry_count(self, task_id: str) -> int:
        """
        Increment and return the workflow retry count for a task

        Args:
            task_id: Task identifier
        Returns:
            int: The updated retry count after incrementing
        """
        try:
            retry_key = f"workflow_retry_count:{task_id}"
            # Increment the counter (creates it with value 1 if doesn't exist)
            new_count = self.redis_client.incr(retry_key)
            # Set expiration to match task expiration
            self.redis_client.expire(retry_key, self.prime_task_expiration)
            logger.debug(
                f"Incremented retry count for task {task_id} to {new_count}")
            return new_count
        except Exception as e:
            logger.error(f"Failed to increment workflow retry count: {str(e)}")
            return 0

    def get_workflow_retry_count(self, task_id: str) -> int:
        """
        Get the current workflow retry count for a task

        Args:
            task_id: Task identifier
        Returns:
            int: The current retry count (0 if key doesn't exist)
        """
        try:
            retry_key = f"workflow_retry_count:{task_id}"
            count = self.redis_client.get(retry_key)
            return int(count) if count else 0
        except Exception as e:
            logger.error(f"Failed to get workflow retry count: {str(e)}")
            return 0

    def has_reached_retry_limit(self, task_id: str, limit: int = 3) -> bool:
        """
        Check if the workflow retry count has reached or exceeded the limit

        Args:
            task_id: Task identifier
            limit: Retry count limit (default: 3)
        Returns:
            bool: True if retry count has reached or exceeded the limit
        """
        retry_count = self.get_workflow_retry_count(task_id)
        return retry_count >= limit

    def add_docker_host(self, host: str) -> bool:
        try:
            self.redis_client.sadd(self.docker_hosts_key, host)
            logger.info(f"Added docker host: {host}")
            return True
        except Exception as e:
            logger.error(f"Failed to add docker host: {str(e)}")
            return False

    def get_docker_hosts(self) -> set:
        try:
            hosts = self.redis_client.smembers(self.docker_hosts_key)
            return hosts
        except Exception as e:
            logger.error(f"Failed to get docker hosts: {str(e)}")
            return set()
