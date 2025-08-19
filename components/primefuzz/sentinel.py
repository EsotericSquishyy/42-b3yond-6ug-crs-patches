import asyncio
import json
import logging
import aio_pika
from typing import Optional
from modules.redis_middleware import RedisMiddleware
from modules.config import Config

logger = logging.getLogger(__name__)


class TaskSentinel:
    def __init__(self, config: Config):
        self.config = config
        self.redis = RedisMiddleware()
        self.check_interval = 1500  # 25 minutes
        self.queue_name = config.queue_name
        self.max_requeue_count = 2
        self.task_requeue_count = {}

    async def connect_mq(self) -> Optional[aio_pika.Connection]:
        """Connect to RabbitMQ"""
        try:
            connection = await aio_pika.connect_robust(
                host=self.config.rabbitmq_host,
                port=self.config.rabbitmq_port,
                login=self.config.rabbitmq_user,
                password=self.config.rabbitmq_password,
            )
            return connection
        except Exception as e:
            logger.warning(f"RabbitMQ down: {e}")
            return None

    async def requeue_task(self, payload: dict) -> bool:
        """Requeue task to RabbitMQ"""
        try:
            taskid = payload.get('task_id')

            # Check requeue count using class dictionary
            current_count = self.task_requeue_count.get(taskid, 0)
            
            # Check if already requeued max times
            if current_count >= self.max_requeue_count:
                logger.warning(
                    f"Task {taskid} has already been requeued {current_count} times. Not requeuing again.")
                return False

            connection = await self.connect_mq()
            if not connection:
                return False

            channel = await connection.channel()
            queue = await channel.declare_queue(
                self.queue_name,
                durable=True
            )

            message = aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            # Use the default exchange's publish method instead of basic_publish
            await channel.default_exchange.publish(
                message,
                routing_key=self.queue_name
            )

            await connection.close()

            # Increment and save requeue count in the class dictionary
            self.task_requeue_count[taskid] = current_count + 1
            logger.info(
                f"Requeued stalled task {taskid} (requeue attempt {self.task_requeue_count[taskid]}/{self.max_requeue_count})")
            return True

        except Exception as e:
            logger.error(f"Failed to requeue task: {e}")
            return False

    async def check_stalled_tasks(self):
        """Check for stalled tasks and requeue them if needed"""
        active_tasks = self.redis.get_active_tasks()
        if not active_tasks:
            logger.info("No active tasks found.")

        for task_id in active_tasks:
            try:
                # Get task payload
                payload = self.redis.get_task_payload(task_id)
                if not payload:
                    continue

                # Check if any payload value is a valid dict
                has_dict = any(
                    isinstance(json.loads(v), dict) if isinstance(v, str) and v.startswith('{')
                    else isinstance(v, dict)
                    for v in payload.values()
                )

                has_dict = has_dict or isinstance(payload, dict)

                if not has_dict:
                    print(
                        f"Task {task_id} payload does not contain a valid dict.")
                    continue

                # Check task status and metrics
                status = self.redis.get_global_task_status(task_id)
                latest_metrics = self.redis.get_latest_task_metrics(task_id)

                if status == "processing" and latest_metrics is None:
                    # Task appears stalled - requeue it
                    await self.requeue_task(payload)
                    logger.info(f"Detected stalled task {task_id}")

            except Exception as e:
                logger.error(f"Error checking task {task_id}: {e}")
                continue

    async def run(self):
        """Main sentinel loop"""
        logger.info("Starting Task Sentinel service...")
        while True:
            try:
                # Sleep at first
                await asyncio.sleep(self.check_interval)
                await self.check_stalled_tasks()
            except Exception as e:
                logger.error(f"Sentinel error: {e}")
                # Sleep on error to prevent tight loop
                await asyncio.sleep(60)
