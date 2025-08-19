import json
import logging
import aio_pika
import sys
from typing import Callable, Dict, Optional
from aio_pika.abc import (
    AbstractRobustConnection,
    AbstractRobustChannel,
)

logger = logging.getLogger(__name__)


class MessageConsumer:
    def __init__(
        self,
        host: str,
        port: int,
        queue_name: str,
        user: str = "user",
        password: str = "secret",
        priority_queue: bool = False,
    ):
        self.host = host
        self.port = port
        self.queue_name = queue_name
        self.user = user
        self.password = password
        self.priority_queue = priority_queue
        self._logger = logger
        self._connection: Optional[AbstractRobustConnection] = None
        self._running = False

    async def start(self, callback_func: Callable[[Dict], None]):
        self._running = True
        self._connection = await aio_pika.connect_robust(
            f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/"
        )
        self._connection.reconnect_callbacks.add(self._on_connection_reconnected)
        self._connection.close_callbacks.add(self._on_connection_closed)

        try:
            channel = await self._connection.channel()
            channel.close_callbacks.add(self._on_channel_closed)

            # Set QoS
            await channel.set_qos(prefetch_count=1)

            try:
                # Try to declare queue with new properties
                queue = await channel.declare_queue(
                    self.queue_name, durable=True, arguments={"x-max-priority": 10}
                ) if self.priority_queue else await channel.declare_queue(self.queue_name, durable=True)
            except aio_pika.exceptions.ChannelPreconditionFailed:
                logger.warning(
                    f"Queue {self.queue_name} exists with different properties. Attempting to recreate..."
                )
                # Delete existing queue
                await channel.queue_delete(self.queue_name)
                # Declare queue with new properties
                queue = await channel.declare_queue(
                    self.queue_name, durable=True, arguments={"x-max-priority": 10}
                ) if self.priority_queue else await channel.declare_queue(self.queue_name, durable=True)
            except (aio_pika.exceptions.AMQPConnectionError, aio_pika.exceptions.ChannelInvalidStateError) as e:
                # try again
                logger.error(f"Error declaring queue, last attempt: {str(e)}")
                queue = await channel.declare_queue(self.queue_name, durable=True)
            except Exception as e:
                logger.error(f"Error declaring queue, last attempt: {str(e)}")
                queue = await channel.declare_queue(self.queue_name, durable=True)

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    if not self._running:
                        break
                    try:
                        await callback_func(message)
                        logger.info("Message processed with callback function.")
                    except (aio_pika.exceptions.ChannelClosed, aio_pika.exceptions.ConnectionClosed) as e:
                        logger.error(f"Channel closed: {str(e)}")
                        break  # Exit loop instead of sys.exit(1)
                    except Exception as e:
                        logger.error(f"Error processing message: {str(e)}")
        except Exception as e:
            logger.error(f"Error in consumer start: {str(e)}")

    def _on_connection_closed(self, connection: AbstractRobustConnection, reason: Optional[BaseException]):
        self._logger.warning(
            f"Connection was closed. Reason: {reason if reason else 'N/A'}. RobustConnection will attempt to reconnect.")

    def _on_connection_reconnected(self, connection: AbstractRobustConnection):
        self._logger.info(
            f"Connection re-established: {connection}. Channel and consumer should be restored by robust components.")

    def _on_channel_closed(self, channel: AbstractRobustChannel, reason: Optional[BaseException]):
        self._logger.warning(
            f"Channel {channel.number if channel else 'N/A'} was closed. Reason: {reason if reason else 'N/A'}")
        if isinstance(reason, aio_pika.exceptions.ChannelInvalidStateError) and "No active transport" in str(reason):
            self._logger.error(
                "Channel closed because connection (transport) is not active. RobustConnection should be attempting to reconnect.")

    async def stop(self):
        """Gracefully stop the consumer"""
        self._running = False
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            self._logger.info("Consumer stopped gracefully")
