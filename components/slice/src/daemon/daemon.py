from pathlib import Path
import threading
import time
import logging
import uuid
import json
import shutil
import os
import tarfile
import docker

from config.config import Config
from daemon.modules.patchrunner import PatchManager
from daemon.modules.slicerunner import SliceRunner
from daemon.modules.workspace import WorkspaceManager
from utils.thread import ExceptionThread
from utils.docker_slice import _env_to_docker_args, docker_run
from daemon.modules.telemetry import create_span, set_span_status, log_event, span_decorator, extract_span_context, get_current_span

from db.db import DBConnection
from daemon.slice_msg import SliceMsg
from db.models.directed_slice import DirectedSlice
from db.models.sarif_slice import SarifSlice

class SliceDaemon:
    def __init__(self, msg_queue, debug = False, mock = False):
        self.agent_config = Config()
        self.tasks = []
        self.task_lock = threading.Lock()
        self.msg_queue = msg_queue
        self.task_thread = ExceptionThread(target=self._task_thread)
        self.task_thread.start()
        self.task_retries = {}  # Track retry counts for each task
        self.max_retries = int(os.getenv('MAX_RETRIES', 3))  # Get max retries from env or use default

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

    def _on_message(self, ch, method, properties, body):
        logging.info('New message received')
        
        carrier = properties.headers or {}
        logging.info(f"Received carrier from headers: {carrier}")
        
        context = None
        remote_span = None
        span_context = None
        
        if carrier:
            try:
                context = extract_span_context(carrier)
                if context:
                    logging.info(f"Extracted span context: {context}, type: {type(context)}")
                    try:
                        remote_span = get_current_span(context)
                        if remote_span:
                            span_context = remote_span.get_span_context()
                            logging.info(f"Span context: {span_context}, type: {type(span_context)}")
                        else:
                            logging.warning("Failed to get remote span from context")
                    except Exception as e:
                        logging.error(f"Failed to get span from context: {e}")
            except Exception as e:
                logging.error(f"Failed to extract span context: {e}")

        with create_span("Slice-14 received slice request", parent_span=None, attributes={
            "crs.action.category": "slice",
            "message_type": "slice_request"
        }) as root_span:
            if context:
                root_span.add_link(context=span_context)
                logging.info(f"Created service link")
                
            try:
                msg = self._parse_message(body)
                
                # Check if we've exceeded retry limit for this task
                if msg.task_id in self.task_retries:
                    self.task_retries[msg.task_id] += 1
                else:
                    self.task_retries[msg.task_id] = 1
                
                log_event(root_span, "task_retry_count", {
                    "task_id": msg.task_id,
                    "retry_count": self.task_retries[msg.task_id]
                })
                
                db_connection = DBConnection(db_url=os.getenv('DATABASE_URL'))
                empty_result_path = self._prepare_empty_result(msg)
                
                # If max retries reached, use empty result and don't attempt processing
                if self.task_retries[msg.task_id] > self.max_retries:
                    log_event(root_span, "max_retries_exceeded", {
                        "task_id": msg.task_id,
                        "max_retries": self.max_retries
                    })
                    result_path = empty_result_path
                else:
                    try:
                        result_path = self._process_slice(msg, root_span)
                    except Exception as e:
                        log_event(root_span, "slice_processing_error", {
                            "task_id": msg.task_id,
                            "error": str(e),
                            "attempt": self.task_retries.get(msg.task_id, 1)
                        })
                        raise
                
                self._write_results_to_db(db_connection, msg.slice_id, msg.is_sarif, result_path)
                
                # On success (after writing to DB), reset retry counter
                if msg.task_id in self.task_retries:
                    del self.task_retries[msg.task_id]
                
                set_span_status(root_span, "OK")
                
            except Exception as e:
                log_event(root_span, "critical_error", {"error": str(e)})
                set_span_status(root_span, "ERROR", str(e))
                raise
    
    def _parse_message(self, body):
        try:
            msg = SliceMsg(**json.loads(body))
            logging.debug(msg)
            return msg
        except Exception as e:
            logging.error('Failed to parse message: <%s | %s>', json.loads(body), e)
            raise
    
    def _prepare_empty_result(self, msg):
        crs_storage_dir = os.getenv('STORAGE_DIR')
        if not crs_storage_dir:
            return None
            
        if not Path(crs_storage_dir).exists():
            Path(crs_storage_dir).mkdir(parents=True, exist_ok=True)
        
        # Use a fixed directory for empty results
        worker_sliceout_dir = Path(crs_storage_dir) / 'slice_results' / 'FAIL-FAIL-FAIL-FAIL-FAIL-FAIL'
        worker_sliceout_dir.mkdir(parents=True, exist_ok=True)
        
        # Create empty result file based on slice type
        empty_result_path = worker_sliceout_dir / ('result_sarif' if msg.is_sarif else 'result_directed')
        
        # Create file with FAIL content
        with open(empty_result_path, 'w') as f:
            f.write('')
            
        return empty_result_path
    
    def _process_slice(self, msg, span):
        # create workspace for the task
        with WorkspaceManager(self.agent_config.tmp_dir, msg) as workspace:
            workspace.copy_and_extract_repos()

            focused_repo = workspace.get_focused_repo()
            if not focused_repo:
                logging.error(f"Focused repo {msg.focus} not found.")
                raise ValueError(f"Focused repo {msg.focus} not found")
            
            # Derive project name and slice target function paths from the message.
            project_name = msg.project_name
            slice_target = msg.slice_target

            # Patch the focused repo with the diff.
            patcher = PatchManager(workspace)
            if patcher.diff_path is not None and not patcher.apply_patch():
                logging.error("Failed to apply patch to the focused repo.")
                raise ValueError("Failed to apply patch to the focused repo")

            # Instantiate and prepare the SliceRunner.
            runner = SliceRunner(project_name, workspace, slice_target, span=span)
            if not runner.prepare():
                logging.error("SliceRunner preparation failed for project %s", project_name)
                raise ValueError(f"SliceRunner preparation failed for project {project_name}")

            # Run the slice analysis for all harnesses
            if not runner.run_slice():
                logging.error("Slice analysis failed for all harnesses in project %s", project_name)
                raise ValueError(f"Slice analysis failed for all harnesses in project {project_name}")
            
            # Results are now handled per-harness inside run_slice()
            
            # Store the slice results.
            crs_storage_dir = os.getenv('STORAGE_DIR')
            if crs_storage_dir:
                worker_sliceout_dir = Path(crs_storage_dir) / 'slice_results' / str(workspace.worker_id)
                shutil.copytree(runner.slice_out, worker_sliceout_dir)
                
                result_file_name = 'merged_slice_result.txt'
                
                crs_result_file_path = worker_sliceout_dir / result_file_name
                
                if not crs_result_file_path.exists():
                    raise FileNotFoundError(f"Slice result file not found: {crs_result_file_path}")
                
                return crs_result_file_path
            else:
                logging.warning('STORAGE_DIR not set, skipping storage of slice results')
                return None
    
    def _write_results_to_db(self, db_connection, slice_id, is_sarif, result_path):
        if not result_path:
            logging.warning("No result path available for database write")
            return
            
        try:
            if is_sarif:
                db_connection.write_to_db(SarifSlice(sarif_id=str(slice_id), result_path=str(result_path)))
            else:
                db_connection.write_to_db(DirectedSlice(directed_id=str(slice_id), result_path=str(result_path)))
        except Exception as e:
            logging.error(f"Failed to write to database: {e}")
            raise