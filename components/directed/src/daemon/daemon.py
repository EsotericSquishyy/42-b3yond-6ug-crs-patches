from pathlib import Path
import threading
import time
import logging
from typing import List
import uuid
import json
import shutil
import os
import tarfile
import docker
import redis
import re
from redis.sentinel import Sentinel
from dataclasses import asdict
from config.config import Config
import pika

from sqlalchemy import select

from daemon.modules.patch_runner import PatchManager
from daemon.modules.fuzzer_runner import FuzzerRunner
from daemon.modules.workspace import WorkspaceManager
from db.models.directed_slice import DirectedSlice
from utils.msg import MsgQueue, SkipTaskException
from utils.thread import ExceptionThread
from utils.docker_utils import _env_to_docker_args, docker_run
from utils.target_utils import is_jvm_project

from db.db import DBConnection
from daemon.directed_msg import DirectedMsg
from daemon.slice_msg import SliceMsg
from daemon.modules.telemetry import log_telemetry_action, span_decorator, create_span, set_span_status, inject_span_context

from utils.misc import generate_random_sha256

class DirectedDaemon:
    def __init__(self, msg_queue: MsgQueue, debug = False, mock = False, redis_url = None):
        self.agent_config = Config()
        self.tasks = []
        self.task_retry_limit = os.getenv('TASK_RETRY_LIMIT', 5)
        self.task_attempts = {}
        self.redis_sentinel_hosts = os.environ.get("REDIS_SENTINEL_HOSTS", "crs-redis-sentinel:26379")
        self.redis_master = os.environ.get("REDIS_MASTER", "mymaster")
        self.redis_password = os.environ.get("REDIS_PASSWORD", None)
        
        # Parse sentinel hosts from string to list of tuples
        sentinel_hosts = [(h, int(p)) for h, p in (item.split(":") for item in self.redis_sentinel_hosts.split(","))]
        
        # Initialize Sentinel
        self.sentinel = Sentinel(sentinel_hosts, socket_timeout=5.0, password=self.redis_password)
        
        # Get master for the specified master name
        self.redis_client = self.sentinel.master_for(
            self.redis_master,
            socket_timeout=5.0,
            password=self.redis_password,
            db=0,
            decode_responses=True
        ) 
        self.task_lock = threading.Lock()
        self.msg_queue = msg_queue
        self.task_thread = ExceptionThread(target=self._task_thread)
        self.task_thread.start()
        self.current_span = None

    def _get_task_metadata(self, task_id: str):
        try:
            task_metadata = self.redis_client.get(f"global:task_metadata:{task_id}")
            logging.info("redis_client.get(f'global:task_metadata:{task_id}'): %s", task_metadata)
            if task_metadata:
                return json.loads(task_metadata)
        except Exception as e:
            logging.error(f"Error getting task metadata for task {task_id}: {e}")
            return None

    @span_decorator("Sends a slice request to the specified queue and waits for the result")
    def _send_slice_request_and_wait(self, slice_queue_name: str, slice_msg_data: SliceMsg, task_id: str) -> Path | None:
        """Sends a slice request to the specified queue and waits for the result."""
        log_telemetry_action(title="Slicing requested",msg_list=[f"Slice message: {slice_msg_data}"],action_name="send_slice_request_and_wait",status="OK",level="info")
        carrier = {}
        carrier = inject_span_context(carrier, self.current_span)
        
        msg_queue = MsgQueue(os.getenv('RABBITMQ_URL'), slice_queue_name)
        message_body = json.dumps(asdict(slice_msg_data))
        properties = pika.BasicProperties(
            headers=carrier,
            content_type='application/json',
            delivery_mode=2
        )
        msg_queue.send(message_body, properties=properties)
        msg_queue.close()

        db_connection = DBConnection(db_url=os.getenv('DATABASE_URL'))
        current_time = 0
        slice_results = None
        db_connection.start_session()
        result_path = None
        while True:
            stmt = select(DirectedSlice).where(DirectedSlice.directed_id == slice_msg_data.slice_id)
            slice_results: List[DirectedSlice] = db_connection.execute_stmt_with_session(stmt)
            logging.debug("Waiting for slice results for task %s (slice_id: %s) from queue %s", task_id, slice_msg_data.slice_id, slice_queue_name)
            log_telemetry_action(title="Slicing waiting",msg_list=[f"Task ID: {task_id}, Slice ID: {slice_msg_data.slice_id}, Queue: {slice_queue_name}"],action_name="send_slice_request_and_wait",status="OK",level="verbose")
            if slice_results:
                potential_result_path = Path(slice_results[0].result_path)
                if potential_result_path.exists(): # Check if file exists
                    result_path = potential_result_path
                    break
                else:
                    logging.warning('Task %s | Slice result file %s not found yet from queue %s', task_id, potential_result_path, slice_queue_name)
                    log_telemetry_action(title="Slicing waiting",msg_list=[f"Task ID: {task_id}, Slice ID: {slice_msg_data.slice_id}, Queue: {slice_queue_name}"],action_name="send_slice_request_and_wait",status="OK",level="verbose")
            #else: # No need for explicit else here, fall through to timeout check
            current_time += 10
            if current_time > self.agent_config.max_slicing_time:
                logging.error('Task %s | Slice timeout for slice_id %s from queue %s', task_id, slice_msg_data.slice_id, slice_queue_name)
                log_telemetry_action(title="Slicing timeout",msg_list=[f"Slice message: {slice_msg_data}"],action_name="send_slice_request_and_wait",status="ERROR",level="debug")
                break
            time.sleep(10)
        
        db_connection.stop_session()
        return result_path

    def _task_thread(self):
        # start consume the message queue
        while True:
            try:
                # self.msg_queue.consume(self._on_message)
                self.msg_queue.threaded_consume(self._on_message)
            except Exception as e:
                logging.error('Failed to consume message: %s', e)
                # time.sleep(10)
                exit(1)

    @span_decorator("Parse and validate the incoming message")
    def _parse_and_validate_message(self, body):
        """Parse and validate the incoming message."""
        try:
            dmsg = DirectedMsg(**json.loads(body))
        except Exception as e:
            logging.error('Failed to parse message: %s', e)
            raise SkipTaskException(None, 'Invalid message format')
        
        # Check task retry limit
        self.task_attempts.setdefault(dmsg.task_id, 0)
        self.task_attempts[dmsg.task_id] += 1
        log_telemetry_action(title="Task attempt",msg_list=[f"Task ID: {dmsg.task_id}, Attempt: {self.task_attempts[dmsg.task_id]}"],action_name="on_message",status="OK",level="info")
        
        if self.task_attempts[dmsg.task_id] > self.task_retry_limit:
            logging.error(f"Task {dmsg.task_id} exceeded retry limit ({self.task_retry_limit}), discarding.")
            log_telemetry_action(title="Task exceeded retry limit",msg_list=[f"Task ID: {dmsg.task_id}, Retry limit: {self.task_retry_limit}"],action_name="on_message",status="ERROR",level="debug")
            del self.task_attempts[dmsg.task_id]
            return None
            
        if dmsg.task_type == 'full':
            logging.error('Task %s | Unsupported fuzz type: %s', dmsg.task_id, dmsg.task_type)
            log_telemetry_action(title="Unsupported fuzz type",msg_list=[f"Task ID: {dmsg.task_id}, Task type: {dmsg.task_type}"],action_name="on_message",status="ERROR",level="debug")
            raise SkipTaskException(dmsg.task_id, 'Unsupported fuzz type')
            
        return dmsg

    @span_decorator("prepare_workspace")
    def _prepare_workspace(self, dmsg):
        """Prepare the workspace for the task."""
        workspace = WorkspaceManager(self.agent_config.tmp_dir, dmsg)
        workspace.__enter__()
        workspace.copy_and_extract_repos()
        
        # Check if JVM project
        oss_fuzz_path = workspace.helper_path.parent.parent
        if is_jvm_project(oss_fuzz_path, dmsg.project_name):
            logging.warning('Task %s | JVM project detected, skipping', dmsg.task_id)
            log_telemetry_action(title="JVM project detected",msg_list=[f"Task ID: {dmsg.task_id}"],action_name="on_message",status="OK",level="info")
            del self.task_attempts[dmsg.task_id]
            return None
            
        focused_repo = workspace.get_focused_repo()
        if not focused_repo:
            logging.error(f"Focused repo {dmsg.focus} not found.")
            log_telemetry_action(title="Focused repo not found",msg_list=[f"Task ID: {dmsg.task_id}, Focus: {dmsg.focus}"],action_name="on_message",status="ERROR",level="debug")
            raise
            
        return workspace

    @span_decorator("handle_delta_fuzzing")
    def _handle_delta_fuzzing(self, dmsg, workspace):
        """Handle delta fuzzing specific tasks."""
        logging.info('Task %s | Delta fuzzing', dmsg.task_id)
        log_telemetry_action(title="Delta fuzzing",msg_list=[f"Task ID: {dmsg.task_id}"],action_name="on_message",status="OK",level="info")
        
        patcher = PatchManager(workspace)
        patcher.apply_patch()
        modified_functions = patcher.get_modified_functions()
        logging.debug('Task %s | Modified functions: %s', dmsg.task_id, modified_functions)
        log_telemetry_action(title="Modified functions",msg_list=[f"Task ID: {dmsg.task_id}, Modified functions: {modified_functions}"],action_name="on_message",status="OK",level="verbose")
        
        changed_functions = patcher.transform_results_with_md5(modified_functions)
        log_telemetry_action(title="Changed functions",msg_list=[f"Task ID: {dmsg.task_id}, Changed functions: {changed_functions}"],action_name="on_message",status="OK",level="verbose")
        
        if not changed_functions:
            logging.warning('Task %s | No changed functions detected in the patch', dmsg.task_id)
            log_telemetry_action(title="No changed functions",msg_list=[f"Task ID: {dmsg.task_id}"],action_name="on_message",status="ERROR",level="debug")
            
        # Special handling for libpng
        if dmsg.project_name == 'libpng':
            for entry in changed_functions:
                logging.debug("Slice target | %s", entry)
                entry[1] = 'OSS_FUZZ_' + entry[1]
                
        return changed_functions

    @span_decorator("handle_slicing")
    def _handle_slicing(self, dmsg, changed_functions):
        """Handle the slicing process."""
        if not dmsg.sarif_slice_path:
            result_path = self._try_r14_slicing(dmsg, changed_functions)
            if result_path and result_path.exists() and result_path.stat().st_size > 0:
                logging.info('Task %s | Slicing R14 successful, result_path: %s', dmsg.task_id, result_path)
                log_telemetry_action(title="Slicing R14 successful",msg_list=[f"Result path: {result_path}"],action_name="on_message",status="OK",level="verbose")
                return result_path
            else:
                logging.error('Task %s | Slicing R14 failed, trying R18', dmsg.task_id)
                return self._try_r18_slicing(dmsg, changed_functions)
        else:
            return self._handle_provided_slice(dmsg)

    @span_decorator("Try Slice-14")
    def _try_r14_slicing(self, dmsg, changed_functions):
        """Handle dynamic slicing with R14 and R18 queues."""
        slice_id_r14 = generate_random_sha256()
        slice_msg = SliceMsg(task_id=dmsg.task_id, 
                            is_sarif=False, 
                            slice_id=slice_id_r14, 
                            project_name=dmsg.project_name, 
                            focus=dmsg.focus, 
                            repo=dmsg.repo, 
                            fuzzing_tooling=dmsg.fuzzing_tooling, 
                            diff=dmsg.diff, 
                            slice_target=list(changed_functions))

        logging.debug("Attempting slice with R14 queue: %s", slice_msg)
        log_telemetry_action(title="Slicing R14 started",msg_list=[f"Slice message: {slice_msg}"],action_name="on_message",status="OK",level="info")
        
        result_path = self._send_slice_request_and_wait(
            slice_queue_name=os.getenv('SLICE_TASK_QUEUE'),
            slice_msg_data=slice_msg,
            task_id=dmsg.task_id
        )
        return result_path

    @span_decorator("Try Slice-18")
    def _try_r18_slicing(self, dmsg, changed_functions):
        """Try slicing with R18 queue after R14 failure."""
        # reason = "empty" if result_path and result_path.exists() and result_path.stat().st_size == 0 else "not found"
        # log_telemetry_action(title="Slicing R14 failed",msg_list=[f"Reason: {reason}"],action_name="on_message",status="ERROR",level="debug")
        
        slice_id_r18 = generate_random_sha256()
        slice_msg_r18 = SliceMsg(task_id=dmsg.task_id,
                                is_sarif=False,
                                slice_id=slice_id_r18,
                                project_name=dmsg.project_name,
                                focus=dmsg.focus,
                                repo=dmsg.repo,
                                fuzzing_tooling=dmsg.fuzzing_tooling,
                                diff=dmsg.diff,
                                slice_target=list(changed_functions))
        
        logging.debug("Attempting slice with R18 queue: %s", slice_msg_r18)
        log_telemetry_action(title="Switching to R18 queue",msg_list=[f"Slice message: {slice_msg_r18}"],action_name="on_message",status="OK",level="info")
        
        result_path = self._send_slice_request_and_wait(
            slice_queue_name=os.getenv('SLICE_TASK_QUEUE_R18'),
            slice_msg_data=slice_msg_r18,
            task_id=dmsg.task_id
        )
        
        if result_path and result_path.exists() and result_path.stat().st_size > 0:
            logging.info('Task %s | Slicing R18 successful, result_path: %s', dmsg.task_id, result_path)
            log_telemetry_action(title="Slicing R18 successful",msg_list=[f"Result path: {result_path}"],action_name="on_message",status="OK",level="verbose")
            return result_path
            
        logging.error('Task %s | Slicing with R18 queue also failed or produced an empty/invalid file.', dmsg.task_id)
        if not result_path or not result_path.exists():
            log_telemetry_action(title="Slicing R18 failed",msg_list=[f"Reason: not found"],action_name="on_message",status="ERROR",level="debug")
            raise FileNotFoundError('Slice result file not found after R18 attempt')
        elif result_path.stat().st_size == 0:
            log_telemetry_action(title="Slicing R18 failed",msg_list=[f"Reason: empty"],action_name="on_message",status="ERROR",level="debug")
            logging.error('Task %s | Slice result file from R18 queue is empty', dmsg.task_id)
            return result_path
            
        return result_path

    @span_decorator("handle_provided_slice")
    def _handle_provided_slice(self, dmsg):
        """Handle the case where sarif_slice_path is provided."""
        result_path = Path(dmsg.sarif_slice_path)
        if not result_path.exists() or result_path.stat().st_size == 0:
            logging.error('Task %s | Provided sarif_slice_path %s is invalid or file is empty.', dmsg.task_id, result_path)
            log_telemetry_action(title="Slicing failed",msg_list=[f"Reason: invalid or empty"],action_name="on_message",status="ERROR",level="debug")
            raise SkipTaskException(dmsg.task_id, "Provided sarif_slice_path is invalid or file is empty.")
        return result_path

    @span_decorator("prepare_and_run_fuzzer")
    def _prepare_and_run_fuzzer(self, dmsg, workspace, result_path):
        """Prepare and run the fuzzer."""
        fuzzer_runner = FuzzerRunner(dmsg, workspace)
        if not fuzzer_runner.prepare():
            logging.error(f"Failed to prepare FuzzerRunner for project '{dmsg.project_name}'")
            log_telemetry_action(title="FuzzerRunner preparation failed",msg_list=[f"Project: {dmsg.project_name}"],action_name="on_message",status="ERROR",level="debug")
            raise
            
        harnesses = fuzzer_runner.detect_fuzz_targets()
        logging.debug('Task %s | Detected Fuzz Targets: %s', dmsg.task_id, harnesses)
        log_telemetry_action(title="Fuzz targets detected",msg_list=[f"Task ID: {dmsg.task_id}, Fuzz targets: {harnesses}"],action_name="on_message",status="OK",level="info")

        self._store_fuzz_targets(dmsg, harnesses, fuzzer_runner)
        self._run_fuzzing(dmsg, fuzzer_runner, harnesses)
        
        return fuzzer_runner

    @span_decorator("store_fuzz_targets")
    def _store_fuzz_targets(self, dmsg, harnesses, fuzzer_runner):
        """Store fuzz targets in storage directory and Redis."""
        storage_dir = Path(os.getenv('STORAGE_DIR')) 
        if not storage_dir.exists():
            logging.error(f"Storage directory {storage_dir} does not exist")
            log_telemetry_action(title="Storage directory not found",msg_list=[f"Storage directory: {storage_dir}"],action_name="on_message",status="ERROR",level="debug")
            raise FileNotFoundError(f"Storage directory {storage_dir} does not exist")
            
        storage_dir = storage_dir / f"directed_fuzz_targets" / dmsg.task_id
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        for harness in harnesses:
            source_path = fuzzer_runner.output_dir / harness
            if source_path.exists():
                shutil.copy2(source_path, storage_dir)

            self.redis_client.set(f"artifacts:{dmsg.task_id}:{harness}:address:directed:after", str(storage_dir / harness))

            fuzzlet = {
                "task_id": dmsg.task_id,
                "harness": harness,
                "sanitizer": "address",
                "fuzz_engine": "directed",
                "artifact_path": str(storage_dir / harness),
            }
            self.redis_client.sadd("b3fuzz:fuzzlets", json.dumps(fuzzlet))
        
        return True

    @span_decorator("run_fuzzing")
    def _run_fuzzing(self, dmsg, fuzzer_runner, harnesses):
        """Run fuzzing for each harness."""
        harness_instances = {harness: str(uuid.uuid4()) for harness in harnesses}
        total_slaves = int(os.getenv('AIXCC_AFL_SLAVE_NUM', '4'))
        num_harnesses = len(harnesses)
        slaves_per_harness = max(1, total_slaves // num_harnesses)
        
        log_telemetry_action(title="Fuzzing started",msg_list=[f"Task ID: {dmsg.task_id}, Harnesses: {harnesses}"],action_name="on_message",status="OK",level="info")
        
        for harness in harnesses:
            with create_span(f"Fuzzing {harness} started", parent_span=self.current_span, attributes={
                "crs.action.category": "directed",
                "message_type": "directed_request"
            }) as span:
                log_telemetry_action(title="Fuzzing started",msg_list=[f"Task ID: {dmsg.task_id}, Harness: {harness}"],action_name="on_message",status="OK",level="verbose")
                instance_id = harness_instances[harness]
                try:
                    file_count = fuzzer_runner.pull_seeds_seedgen(task_id=dmsg.task_id, harness_name=harness)
                    if file_count > 0:
                        fuzzer_runner.run_fuzzer_with_pid(
                            harness, instance_id, corpus_dir=fuzzer_runner.seedgen_dir(harness_name=harness),
                            slaves=slaves_per_harness
                        )
                    else:
                        fuzzer_runner.run_fuzzer_with_pid(harness, instance_id, slaves=slaves_per_harness)
                    fuzzer_runner.start_observer(harness)
                    fuzzer_runner.start_syncer(harness)
                    set_span_status(span, "OK")
                except Exception as e:
                    logging.error(f"Failed to start fuzzer for harness {harness}: {e}")
                    set_span_status(span, "ERROR", description=str(e))
                
        return True

    # @span_decorator("monitor_task_status")
    def _monitor_task_status(self, dmsg, fuzzer_runner):
        """Monitor task status in Redis."""
        redis_key = f"global:task_status:{dmsg.task_id}"
        while True:
            task_status = self.redis_client.get(redis_key)
            if task_status == "canceled":
                logging.warning(f"Task {dmsg.task_id} is canceled. Stopping fuzzing")
                fuzzer_runner.stop_fuzzer()
                del self.task_attempts[dmsg.task_id]
                return
            elif task_status != "processing":
                logging.warning(f"Task {dmsg.task_id} is not in processing or canceled state")
            time.sleep(60)

    def _on_message(self, ch, method, properties, body):
        # Parse and validate message
        dmsg = self._parse_and_validate_message(body)
        if not dmsg:
            return
        
        task_metadata = self._get_task_metadata(dmsg.task_id)
        
        """Main message handler that orchestrates the entire process."""
        with create_span("Incoming directed message", parent_span=None, attributes=task_metadata) as root_span:
            self.current_span = root_span
            logging.info('New message received')
            log_telemetry_action(title="New message received",msg_list=[f"Message: {body}"],action_name="on_message",status="OK",level="verbose")

            # Prepare workspace
            workspace = self._prepare_workspace(dmsg)
            if not workspace:
                return

            try:
                # Handle delta fuzzing if needed
                changed_functions = []
                if dmsg.task_type == 'delta':
                    changed_functions = self._handle_delta_fuzzing(dmsg, workspace)

                # Handle slicing
                result_path = self._handle_slicing(dmsg, changed_functions)

                # Copy slice result to workspace
                focused_repo_path = workspace.get_focused_repo()
                workspace_result_path = focused_repo_path / "aixcc_beyond_allowlist.txt"
                if not result_path:
                    logging.error('Task %s | Slicing result path not found, create a blank file at %s', dmsg.task_id, workspace_result_path)
                    with open(workspace_result_path, 'w') as f:
                        f.write('')
                    result_path = workspace_result_path
                else:
                    shutil.copy(result_path, workspace_result_path)
                    result_path = workspace_result_path

                # Prepare and run fuzzer
                fuzzer_runner = self._prepare_and_run_fuzzer(dmsg, workspace, result_path)

                root_span.end()

                # Create a new span for monitoring
                with create_span("Fuzzing task monitoring", parent_span=None, attributes=task_metadata) as monitor_span:
                    self.current_span = monitor_span
                    # Monitor task status
                    self._monitor_task_status(dmsg, fuzzer_runner)

            except Exception as e:
                logging.error(f"Error processing task {dmsg.task_id}: {e}")
                raise

            workspace.__exit__(None, None, None)
