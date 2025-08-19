import functools
import json
from typing import Dict, List, Tuple

import pika
import pika.spec
from pika.adapters.blocking_connection import BlockingChannel

from patch_generator.env import (
    RABBITMQ_PATCH_PRIORITY,
    RABBITMQ_PATCH_QUEUE,
    RABBITMQ_URL,
)
from patch_generator.logger import init_logger, logger
from patch_generator.utils import PatchMode, is_available_bug_profile, repair


def on_message(
    tasks: List[Tuple[int, PatchMode, int]],
    channel: BlockingChannel,
    method: pika.spec.Basic.Deliver,
    properties: pika.BasicProperties,
    body: bytes,
) -> None:
    try:
        data: Dict = json.loads(body)
        bug_profile_id: int = data["bug_profile_id"]

        ## NOTE: the default patch mode is generic
        patch_mode: PatchMode = PatchMode.from_str(data.get("patch_mode"))
    except (json.JSONDecodeError, KeyError):
        logger.info(f"[🚨] Error parsing message: {body.decode(errors='ignore')}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    logger.info(f"[💬] Received a message: {bug_profile_id}")

    if not is_available_bug_profile(bug_profile_id):
        channel.basic_ack(delivery_tag=method.delivery_tag)
    else:
        channel.basic_publish(
            exchange="",
            routing_key=RABBITMQ_PATCH_QUEUE,
            body=json.dumps(
                {
                    "bug_profile_id": bug_profile_id,
                    "patch_mode": PatchMode.fast.value if patch_mode != PatchMode.none else PatchMode.none.value,
                }
            ),
            properties=pika.BasicProperties(
                delivery_mode=2,
                priority=0,  # Lowest priority
            ),
        )
        channel.basic_ack(delivery_tag=method.delivery_tag)

        if type(properties.priority) is int:
            priority = properties.priority
        else:
            priority = RABBITMQ_PATCH_PRIORITY
        tasks.append((bug_profile_id, patch_mode, priority))
        channel.stop_consuming()


def resend_to_patch_queue(bug_profile_id: int, patch_mode: PatchMode, priority: int) -> None:
    if patch_mode != PatchMode.generic:
        return

    logger.info(f"[🚨] Resending to patch queue: {bug_profile_id}")
    params = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.queue_declare(
        queue=RABBITMQ_PATCH_QUEUE,
        durable=True,
        arguments={"x-max-priority": RABBITMQ_PATCH_PRIORITY},
    )

    channel.basic_publish(
        exchange="",
        routing_key=RABBITMQ_PATCH_QUEUE,
        body=json.dumps(
            {
                "bug_profile_id": bug_profile_id,
                "patch_mode": patch_mode.value,
            }
        ),
        properties=pika.BasicProperties(
            delivery_mode=2,
            priority=max(0, priority - 1),
        ),
    )

    connection.close()


if __name__ == "__main__":
    init_logger()

    while True:
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.basic_qos(prefetch_count=1)

        tasks: List[Tuple[int, PatchMode, int]] = []

        channel.queue_declare(
            queue=RABBITMQ_PATCH_QUEUE,
            durable=True,
            arguments={"x-max-priority": RABBITMQ_PATCH_PRIORITY},
        )
        logger.info(f"[💬] Patch queue declared: {RABBITMQ_PATCH_QUEUE}")

        channel.basic_consume(
            queue=RABBITMQ_PATCH_QUEUE,
            on_message_callback=functools.partial(on_message, tasks),
        )

        logger.info("[💬] Starting consumption")
        channel.start_consuming()
        connection.close()

        for bug_profile_id, patch_mode, priority in tasks:
            try:
                repair(bug_profile_id, patch_mode)
            except Exception as e:
                logger.info(f"[🚨] Error repairing bug profiles: {e}")
                resend_to_patch_queue(bug_profile_id, patch_mode, priority)
                exit(1)
