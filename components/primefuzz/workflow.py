import json
import sys
import tarfile
import os
import asyncio
import logging
import traceback
import aiormq
import aio_pika
from typing import List, Dict
from pathlib import Path

from pamqp import commands as spec

from modules.config import Config
from modules.message_consumer import MessageConsumer
from modules.file_manager import FileManager, delete_folder
from modules.fuzzing_runner import FuzzingRunner
from modules.exceptions import WorkflowError
from modules.patch_manager import PatchManager
from modules.redis_middleware import RedisMiddleware
from modules.log_utils import setup_logging, set_task_context
from utils.target_utils import setup_stop_signal, is_jvm_project, get_task_directory

if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    try:
        from utils.telemetry import log_action
    except Exception as e:
        print(f"Failed to import telemetry module: {e}")
        # Fallback to no-op telemetry logging
        from utils.target_utils import log_action
else:
    print("OTEL_EXPORTER_OTLP_ENDPOINT is not set. Skipping telemetry logging.")
    from utils.target_utils import log_action

setup_logging()
logger = logging.getLogger(__name__)


class FuzzingWorkflow:
    def __init__(self, config: Config):
        self.config = config
        self.message_consumer = MessageConsumer(
            host=config.rabbitmq_host,
            port=config.rabbitmq_port,
            queue_name=config.queue_name,
            user=config.rabbitmq_user,
            password=config.rabbitmq_password,
        )

        self.processed_messages = set()  # Track processed message IDs
        self.file_manager = FileManager()
        # fallback to default oss-fuzz path (if the fuzz-tooling cannot be used)
        self.fuzzing_runner = FuzzingRunner(
            oss_fuzz_path=config.oss_fuzz_path,
            max_workers=config.max_fuzzer_instances,
            monitor_interval=config.metrics_interval,
            crs_dir=config.crs_mount_path,
        )
        self.redis_middleware = RedisMiddleware()
        self.task_priority_map = {}
        # Suffix for original source code backup
        self.orig_src_suffix = "_src_snapshot"
        self.background_tasks = set()

    async def __aenter__(self):
        """Initialize resources when entering context."""
        # Initialize fuzzing runner if needed
        if self.fuzzing_runner:
            await self.fuzzing_runner.setup()
        return self

    async def cleanup(self):
        """Cleanup resources."""
        # Cancel all background tasks
        if self.background_tasks:
            logger.info(
                f"Cancelling {len(self.background_tasks)} background tasks...")
            for task in self.background_tasks:
                if not task.done():
                    task.cancel()

            # Wait for all tasks to complete their cancellation
            if self.background_tasks:
                await asyncio.gather(*self.background_tasks, return_exceptions=True)
            self.background_tasks.clear()

        # Clean up the fuzzing runner
        if self.fuzzing_runner:
            await self.fuzzing_runner.cleanup()
            self.fuzzing_runner = None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def is_message_processed(self, message_id: str) -> bool:
        return message_id in self.processed_messages and message_id != "padding"

    async def mark_message_processed(self, message_id: str) -> None:
        self.processed_messages.add(message_id)

    async def should_skip_task(self, task_id: str) -> bool:
        # Check running processes count
        if (
            len(self.fuzzing_runner.running_processes)
            >= self.config.max_fuzzer_instances
        ):
            logger.info(
                f"Max workers ({self.config.max_fuzzer_instances}) reached, requeueing task..."
            )
            return True

        # Check if task directory exists
        task_dir = get_task_directory(task_id=task_id)
        if task_dir.exists():
            logger.info(
                f"Task directory {task_id} already exists, skipping...")
            return True

        return False

    async def monitor_slice_results(self, task_id: str, message_body: bytes) -> None:
        """
        Background task to monitor slice task results and publish to directed queue.

        Args:
            task_id: The task identifier to monitor
            message_body: Original message body to forward when results are available
        """
        if not self.config.directed_queue or self.config.directed_mode:
            logger.debug(
                f"No directed queue configured, skipping result monitoring for {task_id}"
            )
            return

        logger.info(f"Starting slice result monitoring for task {task_id}")

        # This is to avoid busy waiting
        await asyncio.sleep(self.config.metrics_interval)

        while True:
            try:
                # Check for cancellation
                if asyncio.current_task().cancelled():
                    logger.info(
                        f"Slice monitoring for task {task_id} cancelled")
                    return

                # Check if the task is still active
                if not self.redis_middleware.is_task_active(task_id):
                    logger.info(
                        f"Task {task_id} no longer active, stopping slice result monitoring"
                    )
                    break

                # Get slice task result
                result = self.redis_middleware.get_slice_task_result(task_id)
                if result and result != "/no_results":
                    logger.info(
                        f"Found slice result for task {task_id}, publishing to directed Q {self.config.directed_queue}"
                    )

                    # Create connection to RabbitMQ
                    connection = await aio_pika.connect_robust(
                        host=self.config.rabbitmq_host,
                        port=self.config.rabbitmq_port,
                        login=self.config.rabbitmq_user,
                        password=self.config.rabbitmq_password,
                    )

                    async with connection:
                        channel = await connection.channel()

                        # Declare the queue if it doesn't exist
                        await channel.declare_queue(
                            self.config.directed_queue, durable=True
                        )

                        # Create a message with the original body and add result as a header
                        message = aio_pika.Message(
                            body=message_body, headers={"slice_result": result}
                        )

                        # Publish to the directed queue
                        await channel.default_exchange.publish(
                            message, routing_key=self.config.directed_queue
                        )

                        logger.info(
                            f"Successfully published slice result for task {task_id}"
                        )
                        break  # Stop monitoring after publishing

                # Wait before checking again
                await asyncio.sleep(self.config.metrics_interval)

            except aiormq.exceptions.AMQPConnectionError as e:
                logger.warning(
                    f"RabbitMQ connection error during slice monitoring for task {task_id}: {str(e)}"
                )
                # Continue monitoring with a delay
                await asyncio.sleep(self.config.metrics_interval)

            except aiormq.exceptions.ChannelInvalidStateError as e:
                logger.warning(
                    f"Invalid Channel state or unstable network; {task_id}: {str(e)}"
                )
                # Continue monitoring with a delay
                await asyncio.sleep(self.config.metrics_interval)

            except aio_pika.exceptions.AMQPError as e:
                logger.warning(
                    f"AMQP error during slice monitoring for task {task_id}: {str(e)}"
                )
                # Continue monitoring with a delay
                await asyncio.sleep(self.config.metrics_interval)

            except ConnectionResetError as e:
                logger.warning(
                    f"Connection lost during slice monitoring for task {task_id}: {str(e)}"
                )
                # Continue monitoring with a delay
                await asyncio.sleep(self.config.metrics_interval)
            except asyncio.CancelledError:
                logger.info(f"Slice monitoring for task {task_id} cancelled")
                return

            except Exception as e:
                logger.error(
                    f"Error monitoring slice results for task {task_id}: {str(e)}"
                )
                logger.error(traceback.format_exc())
                await asyncio.sleep(self.config.metrics_interval)

        logger.info(
            f"Task published. Stop slice result monitoring for task {task_id}")

    async def requeue_message_to_end(self, message: aio_pika.IncomingMessage) -> None:
        """Requeues a message by acknowledging it and publishing it to the end of the queue.

        Args:
            message: The message to requeue
        """
        prio = 5
        # update default priority later ^
        try:
            msg_id = message.message_id or "padding"
            if self.task_priority_map.get(msg_id, 5) <= 5:
                prio = prio - 1 if prio > 0 else 0
                self.task_priority_map[msg_id] = prio
            # Get the channel from the message
            channel = message.channel
            # Acknowledge the original message
            await message.ack()

            # Get the queue name from the message consumer
            queue_name = self.message_consumer.queue_name

            # Use the basic_publish method which is more reliably available
            await channel.basic_publish(
                message.body,
                exchange="",  # Use empty string for default exchange
                routing_key=queue_name,
                properties=spec.Basic.Properties(
                    headers=message.headers,
                    delivery_mode=2,  # persistent delivery mode
                ),
            )

            logger.info(f"Message {msg_id} requeued to {queue_name}")
            # Add delay before processing next message
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(
                f"Error requeueing message: {str(e)}. Message dropped.")
            await asyncio.sleep(30)

    async def process_task(self, task: Dict) -> None:
        try:
            task_id = task.get("task_id", "")
            task_type = task.get("task_type", "")
            slice_result = task.get("slice_result", "")

            if not (task_id):
                logger.warning("Invalid Task ID")
                return

            project_name = task.get("project_name")
            focus = task.get("focus", project_name)
            proj_name_with_mode = (
                f"{project_name} (DIRECTED)" if slice_result else project_name
            )
            set_task_context(task_id=task_id, project=proj_name_with_mode)

            # Create sources list from new format
            sources = []
            if task.get("repo"):
                # Handle repo array - take first URL
                for repo in task["repo"]:
                    sources.append({"type": "repo", "url": repo})

            if task.get("fuzzing_tooling"):
                sources.append(
                    {"type": "fuzz-tooling", "url": task["fuzzing_tooling"]})
            if task.get("diff"):
                sources.append({"type": "diff", "url": task["diff"]})

            if not all([task_id, project_name, sources]):
                raise WorkflowError("Missing required fields in task")

            logger.info(
                f"Processing task {task_id} for project {project_name}")

            # Create task directory and download files
            # NOTE: use local path because of the network & performance issue
            task_dir = self.file_manager.create_task_directory(task_id)
            # under /crs
            shared_task_dir = self.file_manager.create_or_get_shared_task_dir(
                task_id)

            # Download and verify files to shared task directory
            downloaded_files = await self.file_manager.download_sources(
                sources, shared_task_dir
            )

            if len(downloaded_files) == 0:
                logger.error(f"Failed to download sources for task {task_id}")
                return None

            # Handle different source types
            repo_source = next(
                (s for s in sources if s["type"] == "repo"), None)
            fuzz_tooling = next(
                (s for s in sources if s["type"] == "fuzz-tooling"), None
            )
            diff_source = next(
                (s for s in sources if s["type"] == "diff"), None)

            if not fuzz_tooling:
                raise WorkflowError("Missing fuzz-tooling source")

            # Extract fuzz-tooling first
            fuzz_tooling_file = next(
                f for f in downloaded_files if Path(f).name.startswith("fuzz-tooling")
            )
            # local /tmp
            fuzz_tooling_path = self.file_manager.extract_archive(
                fuzz_tooling_file, task_dir
            )
            # shared /crs
            shared_fuzz_tooling_path = self.file_manager.extract_archive(
                fuzz_tooling_file, shared_task_dir
            )
            logger.info(
                f"Extracted fuzz-tooling to {fuzz_tooling_path} (local) and {shared_fuzz_tooling_path}"
            )
            oss_fuzz_dir = shared_fuzz_tooling_path.absolute()

            # Update OSS-Fuzz path for runner
            self.fuzzing_runner.oss_fuzz_path = oss_fuzz_dir
            self.fuzzing_runner.local_fuzz_tool_path = fuzz_tooling_path.absolute()
            logger.info(f"Using OSS-Fuzz path: {oss_fuzz_dir}")

            # Initialize project_dir, uncompress the sources under {UUID}/project_name
            project_dir = task_dir / project_name

            # Extract project sources
            source_dir = Path("/non-exists-path")
            if repo_source:
                # NOTE: one file only heres
                repo_file = next(
                    f for f in downloaded_files if Path(f).name.startswith("repo")
                )
                source_dir = self.file_manager.extract_archive(
                    repo_file, project_dir)

            if not source_dir.exists():
                raise WorkflowError(
                    f"Project directory does not exist: {project_dir}")

            # Extract diff if exists
            if diff_source and source_dir.exists():
                diff_file = next(
                    f for f in downloaded_files if Path(f).name.startswith("diff")
                )
                diff_dir = self.file_manager.extract_archive(
                    diff_file, project_dir)

            if diff_source and diff_dir.exists():
                logger.info(
                    f"Applying diff from {diff_dir} under {project_dir}")
                is_jvm = is_jvm_project(oss_fuzz_dir, project_name)
                # backup source code before applying diff, for delta tasks
                backup_name = f"basebuild{self.orig_src_suffix}"
                # copy the tar.gz file insead of the directory
                # self.file_manager.copy_directory(
                #     source_dir,  # original source directory
                #     source_dir.parent / backup_name,
                # )
                # build with primebuilder, but not in directed instance
                if not self.config.directed_mode:
                    self.fuzzing_runner.basebuilder_job_id = None

                # apply the {diff_dir}/ref.diff with the base path at path ${project_dir}
                patch_manager = PatchManager()
                patch_success = await patch_manager.apply_patch(
                    project_dir / focus, diff_dir.absolute()
                )
                if not patch_success:
                    raise WorkflowError("Failed to apply patch")

                if (not self.config.directed_mode) and task_type == "delta" and is_jvm:
                    logger.info(f"[REDIS] added slice task for {project_name}")
                    if not await self.redis_middleware.record_slice_task(
                        task_id, json.dumps(task)
                    ):
                        logger.error(
                            f"Failed to record slice task for {task_id}")

                    # Start background monitoring for slice results
                    task = asyncio.create_task(
                        self.monitor_slice_results(
                            task_id, json.dumps(task).encode())
                    )
                    # Add a callback to remove the task from the set when it completes
                    task.add_done_callback(self.background_tasks.discard)
                    self.background_tasks.add(task)

            # Run fuzzing workflow
            await self.fuzzing_runner.run_workflow(
                project_name=project_name,
                src_path=source_dir,
                task_id=task_id,
                slicing_res=slice_result,
            )

        except tarfile.ReadError as e:
            logger.error(
                f"Tar failed. Skipping task {task.get('task_id')}: {e} .")
            return None

        except RuntimeError as e:
            logger.error(
                f"Failed to build or run task {task.get('task_id')}: {e} .")
            # remove the task directory
            # if "task_id" in locals() and task_id != "":
            #     task_path = Path(task_id)
            #     if task_path.is_dir():
            #         logger.info("cleaning up task directory...")
            #         delete_folder(task_path)

            raise WorkflowError("Failed to build or run task")

        except Exception as e:
            logger.error(
                f"Error processing task: {str(e)}\n{traceback.format_exc()}")
            raise WorkflowError("Unknown error occurred")

    async def process_message(self, message: aio_pika.IncomingMessage) -> None:
        try:
            message_id = message.message_id or "padding"
            payload = {}
            is_fuzz_running = False
            # requeue if already processed
            if await self.is_message_processed(message_id):
                logger.info(f"Message {message_id} already processed, Skip...")
                # await self.requeue_message_to_end(message)
                return

            async with message.process(ignore_processed=True):
                # Check if task has reached retry limit
                task = message.body
                payload = json.loads(task.decode("unicode_escape"))
                task_id = payload.get("task_id")
                task_type = payload.get("task_type", "")
                slice_result = None
                cancel_success = True

                logger.debug("Processing new tasks")
                if task_id and self.redis_middleware.has_reached_retry_limit(task_id):
                    logger.warning(
                        f"Task {task_id} has reached retry limit (3). Skipping further processing."
                    )
                    return

                # should skip for cancel at MQ
                if task_type.strip() == "cancel" and task_id:
                    # Race condition ?
                    await self.redis_middleware.remove_record_task(task_id)
                    # Note: I will merge the predicates later
                    cancel_success = setup_stop_signal(
                        get_task_directory(task_id=task_id)
                    )
                    if cancel_success:
                        return

                # should skip for cancel at Redis
                if self.redis_middleware.get_global_task_status(task_id) == "canceled":
                    cancel_success = True
                    logger.info(
                        f"Task {task_id} is canceled at redis. Skipping...")
                    return

                # requeue on cancel error or no enough workers
                if (not cancel_success) or await self.should_skip_task(task_id):
                    await self.requeue_message_to_end(message)
                    return

                if hasattr(message, "headers"):
                    slice_result = message.headers.get("slice_result", None)
                    if slice_result and self.config.directed_mode:
                        logger.info(
                            f"Received directed fuzzing task {task_id}: {slice_result}"
                        )
                        payload["slice_result"] = slice_result

                # skip recording if slice result is available
                if not self.config.directed_mode:
                    await self.redis_middleware.record_task_data(payload)
                    await self.redis_middleware.record_task(task_id, task_type)

                await self.mark_message_processed(message_id)

            # should be acknowledged here
            if task_id:
                try:
                    is_fuzz_running = True
                    log_action(
                        "fuzzing",
                        "prepare_fuzzers",
                        {"task.id": task_id, "team.id": "b3yond", "round.id": 1},
                        {"fuzz.findings.memo": "pending"},
                    )
                    await self.process_task(payload)
                except WorkflowError as e:
                    logger.error(
                        f"Workflow error during TASK processing: {str(e)}")
                    task_path = Path(task_id)
                    if task_path.is_dir():
                        logger.info("cleaning up task directory...")
                        delete_folder(task_path)

                    # await self.requeue_message_to_end(message)
                    # await self.mark_message_processed(message_id)
                    # sys.exit(1)

        except (
            aiormq.exceptions.AMQPConnectionError,
            aiormq.exceptions.ChannelInvalidStateError,
        ) as e:
            if "task" not in locals():
                task = message.body

            payload = json.loads(task.decode("unicode_escape"))
            task_id = payload.get("task_id", "unknown")
            logger.warning(
                f"Unstable RabbitMQ connection during message processing {task_id}: {str(e)}."
            )
            log_action(
                "fuzzing",
                "failed_fuzzers",
                {"task.id": task_id, "team.id": "b3yond", "round.id": 1},
                {"fuzz.findings.memo": str(e)},
                status="build failed",
            )
            if is_fuzz_running:
                logger.info(
                    "^^ Everything works well if you see the task ID above. ^^")
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Message processing cancelled")
            self.fuzzing_runner.running_processes.clear()
            raise
        except Exception as e:
            self.fuzzing_runner.running_processes.clear()
            logger.error(
                f"Error processing message: {str(e)}\n{traceback.format_exc()}"
            )
            raise

    async def start(self):
        retry_delay_seconds = 60
        retry_count = 0
        max_retries = 30

        while retry_count < max_retries:
            try:
                # log_action(
                #     "fuzzing",
                #     "waiting_tasks",
                #     {"task.id": "NA", "team.id": "b3yond", "round.id": 1},
                #     {"fuzz.findings.memo": "pending"},
                # )
                await self.message_consumer.start(self.process_message)
                # If message_consumer.start() returns, it means the consumer stopped gracefully
                # or was cancelled and handled its own shutdown. We should exit the loop.
                logger.info(
                    "Message consumer stopped. try workflow loop again")
                retry_count += 1
                logger.info(f"Retry attempt {retry_count}/{max_retries}")
                await asyncio.sleep(retry_delay_seconds)

            except (KeyboardInterrupt, asyncio.CancelledError):
                logger.info(
                    "\nShutdown requested. Exiting workflow start loop.")
                break  # Propagate to finally block for cleanup

            except Exception as e:
                logger.warning(
                    f"Message consumer failed with an error: {str(e)}")
                # logger.error(traceback.format_exc())
                retry_count += 1
                logger.info(
                    f"Retry attempt {retry_count}/{max_retries}. Restarting message consumer in {retry_delay_seconds} seconds...")
                await asyncio.sleep(retry_delay_seconds)

        logger.warning(
            f"Maximum retry attempts ({max_retries}) reached. Stopping workflow.")
        logger.info("Performing final cleanup for FuzzingWorkflow...")
        await self.cleanup()

        # Ensure message consumer is closed if it exists and has a close method.
        # This is a safeguard, as message_consumer.start() should call its own close() in its finally block.
        if self.message_consumer and hasattr(self.message_consumer, 'close'):
            try:
                await self.message_consumer.close()
            except Exception as e:
                logger.error(f"Error during final message consumer close: {e}")

        print("FuzzingWorkflow cleanup complete, application will exit.")
