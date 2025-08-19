from datetime import datetime
import logging
import os
from pathlib import Path
import shutil
import tarfile
import threading
import time
import uuid
# ! Why we need PollingObserver: https://stackoverflow.com/questions/76491748/watchdog-is-not-monitoring-the-files-at-all
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from db.db import DBConnection
from db.models.fuzz_related import Bug, Seed, FuzzerTypeEnum
from daemon.directed_msg import DirectedMsg
from daemon.modules.metrics_collector import MetricsCollector

class CrashHandler(FileSystemEventHandler):
    def __init__(self, output_dir: Path, directed_msg: DirectedMsg, harness_name: str, instance_id: str):
        """
        Monitors the given output directory for crash files and records crashes
        in the database using details from the DirectedMsg and the provided harness name.

        Args:
            output_dir (Path): The directory to watch.
            directed_msg (DirectedMsg): Contains task_id and project_name.
            harness_name (str): The harness name to record with the bug.
            instance_id (str): Unique identifier for this fuzzer instance.
        """
        super().__init__()
        self.output_dir = output_dir
        self.directed_msg = directed_msg
        self.task_id = directed_msg.task_id
        self.project_name = directed_msg.project_name
        self.harness_name = harness_name
        self.instance_id = instance_id

        # Set up logging.
        logging.getLogger(self.__class__.__name__).setLevel(logging.INFO)

        # Set up the polling observer.
        self.observer = PollingObserver()
        self.observer.schedule(self, path=str(self.output_dir), recursive=True)

        # Initialize DB connection using the helper.
        db_url = os.getenv('DATABASE_URL')
        self.db_conn = DBConnection(db_url)

        # Add after existing initialization code
        self.queue_archive_thread = threading.Thread(target=self._queue_archive_loop)
        self.queue_archive_thread.daemon = True
        self.running = True
        self.stop_event = threading.Event()

    def on_created(self, event):
        crash_path = Path(event.src_path).resolve()
        if not crash_path.is_file():
            return

        crash_filename = crash_path.name
        parent_dir = crash_path.parent.name

        # Only process valid crash files.
        if parent_dir == 'crashes' and crash_filename != 'README.txt':
            logging.debug(f'[{self.project_name}] Crash detected at {event.src_path}')
            self.handle_crash(crash_path)

    def handle_crash(self, crash_path: Path):
        logging.debug(f'[{self.project_name}] Handling crash file: {crash_path}')

        # Get the storage directory from the CRS_STORAGE environment variable
        storage_dir = os.getenv('STORAGE_DIR')
        if not storage_dir:
            logging.error("STORAGE_DIR environment variable not set.")
            raise ValueError("STORAGE_DIR environment variable not set.")

        # Create the full path: storage_dir/directed_crashes/project_name/task_id
        storage_dir = Path(storage_dir).resolve()
        crash_dir = storage_dir / 'directed_crashes' / self.project_name / self.task_id
        crash_dir.mkdir(parents=True, exist_ok=True)

        # Generate a unique filename to avoid collisions
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        new_filename = f"{timestamp}_{crash_path.name}"
        new_path = crash_dir / new_filename

        # Copy the crash file to the storage directory
        try:
            shutil.copy2(crash_path, new_path)
            logging.debug(f'[{self.project_name}] Crash file copied to storage: {new_path}')
        except Exception as e:
            logging.error(f"Error copying crash file to storage: {e}")
            raise e

        # Create a new Bug record and store the path to the crash file instead of its content.
        bug = Bug(
            task_id=self.task_id,
            architecture="x86_64",
            poc=str(new_path),
            harness_name=self.harness_name,
            sanitizer="address",  # Default to ASAN (address) value
            sarif_report={}
        )
        try:
            self.db_conn.write_to_db(bug)
            logging.debug(f'[{self.project_name}] Bug recorded with ID: {bug.id}')
        except Exception as e:
            logging.error(f"Failed to record bug in DB: {e}")

    def handle_queue_archive(self):
        """Archives the queue directory and stores it in the storage directory as a Seed."""
        afl_dirs = self.output_dir
        master_dir = afl_dirs / 'master'
        
        if master_dir.exists() and master_dir.is_dir():
            directories = [master_dir]
        else:
            # sync_dir is only for sync_seeds
            directories = [d for d in afl_dirs.iterdir() 
                        if d.is_dir() and d.name != 'sync_dir']
        
        for afl_dir in directories:
            queue_dir = afl_dir / 'queue'
            if not queue_dir.exists():
                logging.warning(f'[{self.project_name} / {afl_dir.name}] Queue directory not found: {queue_dir}')
                continue

            # Create directed_seeds directory in storage
            storage_dir = Path(os.getenv('STORAGE_DIR')).resolve()
            seeds_dir = storage_dir / 'directed_seeds'
            seeds_dir.mkdir(parents=True, exist_ok=True)

            # Generate a unique filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            unique_id = uuid.uuid4().hex[:8]
            archive_name = f"queue_{self.harness_name}_{timestamp}_{unique_id}.tar.gz"
            new_path = seeds_dir / archive_name

            try:
                # Create tar archive while excluding .state folder
                def exclude_state(tarinfo):
                    if '.state' in tarinfo.name:
                        return None
                    return tarinfo
                with tarfile.open(new_path, "w:gz") as tar:
                    tar.add(queue_dir, arcname=queue_dir.name, filter=exclude_state)
                
                logging.debug(f'[{self.project_name} / {afl_dir.name}] Queue archived to: {new_path}')

                # Collect metrics before creating Seed record
                metrics_collector = MetricsCollector()
                metrics = metrics_collector.collect_metrics(afl_dir)
            
                # Store as Seed in database
                seed = Seed(
                    task_id=self.task_id,
                    path=str(new_path),
                    harness_name=self.harness_name,
                    fuzzer=FuzzerTypeEnum.directed,
                    instance=self.instance_id,
                    coverage=metrics.get('edges_found'),
                    metric=metrics
                )
                self.db_conn.write_to_db(seed)
                logging.debug(f'[{self.project_name} / {afl_dir.name}] Queue archive recorded as Seed in DB')

            except Exception as e:
                logging.error(f"Error archiving queue directory: {e}")
                raise e

    def _queue_archive_loop(self):
        """Periodically archives the queue directory."""
        while self.running:
            try:
                # stop immediately if stop_event is set
                self.stop_event.wait(timeout=600)
                if not self.stop_event.is_set():    
                    self.handle_queue_archive()
            except Exception as e:
                logging.error(f"[{self.project_name}] Error in queue archive loop: {e}")

    def start(self):
        logging.info(f"Starting CrashHandler poller. Watching: {self.output_dir}")
        self.observer.start()
        self.queue_archive_thread.start()

    def stop(self):
        logging.info("Stopping CrashHandler poller.")
        self.running = False
        self.stop_event.set()
        self.observer.stop()
        self.observer.join()
        self.queue_archive_thread.join()
