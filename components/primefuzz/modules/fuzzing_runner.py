import asyncio
import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import traceback
import psutil
import time
import copy
from typing import List, Dict, Any
from pathlib import Path
from db.db_manager import DBManager
from modules.file_manager import FileManager, create_a_simple_seed_corpus
from modules.metrics_collector import MetricsCollector
from utils.docker_utils import (
    docker_prune,
    docker_stop,
    get_available_dind_hosts,
    get_lowest_cpu_docker_host,
    get_docker_image_id,
)
from utils.target_utils import (
    find_fuzz_targets,
    get_slicing_extra_args,
    kill_process_tree,
    kill_docker_by_name,
    is_jvm_project,
    get_ignore_tokens,
    get_failed_check_build_targets,
    get_sanitizers,
)
from utils.parse_options import is_timeout_handled_libfuzzer
from utils.dict_gen import gen_dict_java
from modules.triage import (
    CrashTriager,
    CrashInfo,
    SanitizerType,
    UNKNOWN_STRING,
    TIMEOUT_STRING,
    PADDING_STRING,
)
from modules.log_utils import set_task_context
from modules.redis_middleware import RedisMiddleware
from modules.artifact_backup import ArtifactBackup
from modules.exceptions import EarlyCancelledTaskError

if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    try:
        from utils.telemetry import log_action_from_metrics, log_action
    except Exception as e:
        print(f"Failed to import telemetry module: {e}")
        # Fallback to local logging
        from utils.target_utils import log_action_from_metrics, log_action
else:
    print("OTEL_EXPORTER_OTLP_ENDPOINT is not set. Skipping telemetry logging.")
    from utils.target_utils import log_action_from_metrics, log_action

logger = logging.getLogger(__name__)


class FuzzingRunner:
    def __init__(
        self,
        oss_fuzz_path: str,
        max_workers: int = 2,
        monitor_interval: int = 60,
        crs_dir: str = "/crs",
        fork_on_seedgen: bool = True,
    ):
        self.oss_fuzz_path = Path(oss_fuzz_path)
        self.local_fuzz_tool_path = Path('/tmp/non-exist-path')
        # the maximum number of concurrent fuzzers
        self.max_workers = max_workers
        # Store running processes for each target
        self.running_processes = {}
        self.monitoring_task = {}
        self.db_manager = DBManager()
        self.metrics_collector = MetricsCollector()
        # in seconds
        self.monitor_interval = monitor_interval
        self.crs_dir = crs_dir
        self.restart_required = set()
        self.dedup_tokens: Dict[str, set] = {}
        self.exit_key = "STOP_NOW"
        self.fork_on_seedgen = fork_on_seedgen
        self.merge_on_seedgen = True
        self.default_fuzzer_args_env = "FUZZER_ARGS="
        self.basebuilder_job_id = None
        self.build_for_all_dind = False
        self.sanitizers = ["address"]

    @property
    def oss_fuzz_path(self):
        return self._oss_fuzz_path

    @oss_fuzz_path.setter
    def oss_fuzz_path(self, path):
        self._oss_fuzz_path = Path(path)

    async def setup(self):
        """Initialize database connection."""
        if not self.db_manager:
            self.db_manager = DBManager()
        # await self.db_manager.init_pool()

    async def cleanup(self):
        """Cleanup resources."""
        if self.db_manager:
            await self.db_manager.cleanup()
            self.db_manager = None

    def set_task_metadata(self, task_id: str, payload: json):
        pass

    def get_task_metadata(self, task_id: str) -> dict:
        return {}

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    def _get_task_key(
        self, taskid_name: str, project_name: str, target: str, suffix: str = ""
    ) -> str:
        """Generate task key with optional suffix"""
        host_id = os.getenv(
            "INSTANCE_ID", socket.gethostname().replace(".", "-"))[-8:]
        return f"{host_id}_{taskid_name}_{project_name}_{target}{suffix}"

    async def _check_running_task(
        self, taskid_name: str, project_name: str, target: str
    ) -> str:
        """Check if task is running and return appropriate task key"""
        suffixes = ["", "_seedgen", "_merged"]

        for suffix in suffixes:
            task_key = self._get_task_key(
                taskid_name, project_name, target, suffix)
            if task_key in self.running_processes:
                if suffix == "_merged":  # Last attempt
                    logger.info(f"Task {task_key} already running, skipping.")
                    return None
                logger.info(
                    f"Task {task_key} already running, trying next variant.")
                continue
            return task_key

        return None

    async def check_global_task_status(self, task_id: str) -> bool:
        """Check Redis for global task cancellation status.

        Args:
            task_id (str): The task identifier to check

        Returns:
            bool: True if monitoring should stop (task canceled), False to continue
        """
        try:
            redis_client = RedisMiddleware()

            status = redis_client.get_global_task_status(task_id)
            logger.debug(
                f"Checking global task status for {task_id}: {status}")

            if status == "canceled":
                logger.debug(f"Task {task_id} marked as canceled in Redis")
                host_id = os.getenv(
                    "INSTANCE_ID", socket.gethostname().replace(".", "-")
                )[-8:]
                stopped = await self.stop_all_fuzzers("", f"{host_id}_{task_id}")
                await redis_client.remove_record_task(task_id)
                if stopped:
                    logger.info(f"Fuzzers stopped for canceled task {task_id}")
                    # no need to await
                    log_action(
                        "fuzzing",
                        "stop_fuzzers",
                        {
                            "task.id": task_id,
                            "team.id": "b3yond",
                            "round.id": "final",
                        },
                        {"fuzz.findings.memo": "cancel"},
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking global task status: {e}")
            return False

    async def check_exit_file(self, fuzz_tool_path: Path, task_id: str) -> bool:
        """Check if exit file exists and handle stopping.

        Returns:
            bool: True if monitoring should stop, False to continue
        """
        exit_file = fuzz_tool_path / self.exit_key
        logger.debug(f"Checking for exit file: {exit_file.absolute()}")

        if exit_file.exists():
            logger.info(
                f"Exit file found, stopping fuzzers for task {task_id}")
            stopped = await self.stop_all_fuzzers("", task_id)
            if stopped:
                exit_file.unlink()
                logger.info(
                    f"Fuzzers stopped for task {task_id}, monitor task will exit"
                )
                return True

        return False

    async def stop_all_fuzzers(
        self, target_process_key: str, target_process_prefix: str | None
    ) -> bool:
        try:
            # Case 1: Stop specific process by key
            if target_process_key in self.running_processes:
                process = self.running_processes[target_process_key]
                await kill_docker_by_name(target_process_key)
                # kill_process_tree(process)
                del self.running_processes[target_process_key]
                logger.info(f"Stopped fuzzer: {target_process_key}")
                return True

            # Case 2: Stop processes by prefix
            if target_process_prefix:
                stopped_any = False
                for process_key in list(self.running_processes.keys()):
                    if process_key.startswith(target_process_prefix):
                        logger.debug(
                            f"Stopping docker container {process_key}")
                        if await kill_docker_by_name(process_key):
                            logger.info(
                                f"Stopped docker container {process_key}")

                        process = self.running_processes[process_key]
                        # kill_process_tree(process)
                        del self.running_processes[process_key]
                        logger.info(
                            f"Stopped fuzzer with prefix match: {process_key}")
                        stopped_any = True
                return stopped_any

            # Case 3: Stop all processes
            if target_process_key == "" and len(self.monitoring_task) > 0:
                for process_key, process in list(self.running_processes.items()):
                    try:
                        await kill_docker_by_name(process_key)
                        kill_process_tree(process)
                        del self.running_processes[process_key]
                        logger.info(f"Stopped fuzzer: {process_key}")
                    except Exception as e:
                        logger.error(
                            f"Error stopping fuzzer {process_key}: {e}")

                for task_id, task in self.monitoring_task.items():
                    if isinstance(task, asyncio.Task):
                        task.cancel()
                    logger.info(f"Cancelled monitoring task: {task_id}")

                self.running_processes.clear()
                self.monitoring_task.clear()
                return True

            return False

        except Exception as e:
            logger.error(f"Error stopping fuzzer {target_process_key}: {e}")
            return False

    async def restart_fuzzer(
        self,
        helper_script: Path,
        task_id: str,
        project_name: str,
        corpus_dir: Path,
        log_dir: Path,
        target: str,
        file_manager: FileManager,
        jazzer_args: str = None,
        enable_fork: bool = True,
    ) -> None:
        """Restart a specific fuzzer process in background."""
        host_id = os.getenv(
            "INSTANCE_ID", socket.gethostname().replace(".", "-"))[-8:]
        target_key = f"{host_id}_{task_id}_{project_name}_{target}"

        try:
            # Stop existing process
            # if target_key in self.running_processes:
            await self.stop_all_fuzzers(
                target_process_key=target_key, target_process_prefix=None
            )

            # Start new process in background
            logger.info(f"Restarting fuzzer: {target}")

            oss_fuzz_path = helper_script.parent.parent
            oss_fuzz_out = oss_fuzz_path / "build" / "out" / project_name

            zip_path = file_manager.create_zip_archive(
                src_path=corpus_dir / target,
                dest_dir=oss_fuzz_out,
                archive_name=f"{target}_seed_corpus",
            )

            logger.info(f"Seed zip updated: {zip_path}")

            # docker_prune()

            asyncio.create_task(
                self.run_single_fuzzer(
                    target=target,
                    helper_script=helper_script,
                    corpus_dir=corpus_dir / target,
                    log_dir=log_dir,
                    project_name=project_name,
                    semaphore=asyncio.Semaphore(1),  # Single restart at a time
                    jazzer_args=jazzer_args,
                    enable_fork=enable_fork,
                    fuzz_tool_path=oss_fuzz_path,
                )
            )

        except Exception as e:
            logger.error(f"Error restarting fuzzer {target}: {e}")
            # Add to retry queue
            self.restart_required.add(target_key)

    async def get_all_running_processes_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about currently running fuzzer processes"""
        process_info = {}

        for target_key, process in self.running_processes.items():
            try:
                p = psutil.Process(process.pid)
                info = {
                    "pid": process.pid,
                    "status": p.status(),
                    "cpu_percent": p.cpu_percent(),
                    "memory_info": p.memory_info()._asdict(),
                    "create_time": time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(p.create_time())
                    ),
                    "running": process.poll() is None,
                }
                process_info[target_key] = info
            except (psutil.NoSuchProcess, ProcessLookupError):
                process_info[target_key] = {"status": "terminated"}
                del self.running_processes[target_key]

        return process_info

    async def get_process_info(self, target_key: str) -> Dict[str, Any]:
        """Get information about a specific running fuzzer process"""
        if target_key not in self.running_processes:
            return None

        try:
            process = self.running_processes[target_key]
            p = psutil.Process(process.pid)
            return {
                "pid": process.pid,
                "status": p.status(),
                "cpu_percent": p.cpu_percent(),
                "memory_info": p.memory_info()._asdict(),
                "create_time": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(p.create_time())
                ),
                "running": process.poll() is None,
            }

        except (psutil.NoSuchProcess, ProcessLookupError):
            del self.running_processes[target_key]
            return {"status": "terminated"}

    async def process_crash_file(
        self,
        crash_file: Path,
        processed_crashes: set,
        crash_backup_dir: Path,
        fuzz_tool_path: Path,
        project_name: str,
        harness_name: str,
        task_id: str,
        file_manager: FileManager,
        is_jvm: bool = False,
        log_file: Path = None,
    ) -> tuple[int, bool]:
        """Process a single crash file and store results."""
        is_restart_required = False
        skip_store_db = False
        # delta_mode = await self.db_manager.get_task_type_by_id(task_id) == "delta"

        if crash_file.name in processed_crashes:
            return len(processed_crashes), is_restart_required

        processed_crashes.add(crash_file.name)
        copied_crash_file = file_manager.copy_file(
            crash_file, crash_backup_dir)

        if copied_crash_file is None:
            logger.warning(
                f"Failed to copy crash file {crash_file.name}, skipping")
            return len(processed_crashes), is_restart_required

        # the crash should not be reproduced in delta mode
        # stop waiting for basebuilder job once failed
        else:
            self.basebuilder_job_id = None

        async with CrashTriager(fuzz_tool_path) as triager:
            crash_info = CrashInfo(
                bug_type=TIMEOUT_STRING if copied_crash_file.name.startswith(
                    "timeout") else UNKNOWN_STRING,
                trigger_point=PADDING_STRING,
                summary=PADDING_STRING,
                raw_output=PADDING_STRING,
                sanitizer=SanitizerType.ASAN.value,
                harness_name=harness_name,
                poc=str(copied_crash_file),
                dup_token="",
                sarif_report={"version": "2.1.0", "runs": []},
            )

            if is_jvm:
                if SanitizerType.JAZZER.value in self.sanitizers:
                    crash_info.sanitizer = SanitizerType.JAZZER.value
                elif len(self.sanitizers) > 0:
                    crash_info.sanitizer = self.sanitizers[0]
                logger.debug(
                    f"Unify the JVM sanitizer: {crash_info.sanitizer}")

            if not (crash_info.dup_token in self.dedup_tokens) and (crash_info.dup_token != ""):
                self.dedup_tokens[crash_info.bug_type] = set()

            if not skip_store_db:
                # can use context manager with db manager
                # async with DBManager() as dbm:
                logger.info(
                    f"Save crash info to db: {copied_crash_file.name} on {harness_name} from {project_name}")
                await self.db_manager.store_bug_profile_info(
                    task_id, crash_info  # , is_jvm
                )

            if (
                crash_info.dup_token.strip() != ""
                and crash_info.bug_type.strip() != TIMEOUT_STRING
            ):
                # Add new token
                self.dedup_tokens[crash_info.bug_type].add(
                    crash_info.dup_token)

            logger.info(
                f"CRASH:\t{crash_file.name} on {harness_name}, Bug type:\t{crash_info.bug_type}\n"
            )

            log_action(
                "dynamic_analysis",
                "prime_crash_triage",
                {"team.id": "b3yond", "task.id": task_id, "round.id": "final"},
                {
                    "crs.action.target.harness": harness_name,
                    "crs.action.target.bug_type": crash_info.bug_type,
                    "crs.action.target.sanitizer": crash_info.sanitizer,
                },
            )

            # Process JVM crash logs if applicable
            if is_jvm and log_file.exists():
                crash_log_info = await triager.triage_crash_log(log_file, harness_name)
                if (
                    crash_log_info.dup_token.strip()
                    and crash_log_info.dup_token.strip() != UNKNOWN_STRING
                ):
                    logger.info(
                        f"Add dup token from crash log: {crash_log_info.dup_token}"
                    )
                    if not (crash_log_info.bug_type in self.dedup_tokens):
                        self.dedup_tokens[crash_log_info.bug_type] = set()

                    # Add new token
                    self.dedup_tokens[crash_log_info.bug_type].add(
                        crash_log_info.dup_token
                    )

            if is_jvm:
                if crash_log_info.bug_type.strip() == TIMEOUT_STRING:
                    logger.info(
                        f"Timeout detected, restart the fuzzer: {harness_name}")
                is_restart_required = True
            else:
                is_restart_required = False

            return len(processed_crashes), is_restart_required

    async def poll_seeds_selected(
        self,
        task_id: str,
        project_name: str,
        harness_name: str,
        corpus_dir: Path,
        file_manager: FileManager,
    ) -> int:
        """Fetch and merge AI selected corpus.

        Args:
            task_id: Task identifier
            project_name: Name of the project
            harness_name: Name of the fuzzer harness
            corpus_dir: Directory to extract corpus to
            file_manager: FileManager instance

        Returns:
            list: List of extracted files, empty if error or no valid files
        """
        try:
            # Get latest selected seeds paths from DB
            paths = await self.db_manager.get_selected_seeds_corpus(
                task_id=task_id, harness_name=harness_name
            )

            if not paths:
                logger.info(
                    f"No selected corpus found for {task_id}/{harness_name}")
                return 0
            else:
                logger.info(
                    f"Found {len(paths)} selected corpus for {task_id}/{harness_name}"
                )

            # Filter out non-seedgen paths
            seedgen_paths = [p for p in paths if harness_name in str(p)]
            if (not seedgen_paths) or len(seedgen_paths) < 1:
                logger.info(
                    f"No seedgen corpus in selected paths for {task_id}/{harness_name}"
                )

            if len(paths) < 1:
                logger.info(
                    "Skip merging selected seeds, no path found.")
                return len(paths)

            # Create temp directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                extracted_files = []

                # Extract each archive
                for archive_path in paths:
                    logger.info(f"Extracting selected corpus: {archive_path}")
                    if not archive_path.endswith(".tar.gz"):
                        continue

                    src_path = Path(archive_path)
                    if not src_path.exists():
                        logger.error(
                            f"Selected corpus not found at {archive_path}")
                        continue

                    extracted_dir = file_manager.extract_archive(
                        src_path, temp_path)
                    extracted_files.extend(list(extracted_dir.glob("*")))

                # Create seed corpus zip if files were extracted
                if extracted_files:
                    oss_fuzz_out = (
                        corpus_dir.parent.parent.parent.parent / "out" / project_name
                    )
                    zip_path = file_manager.create_zip_archive(
                        src_path=temp_path,
                        dest_dir=oss_fuzz_out,
                        archive_name=f"{harness_name}_seed_corpus",
                    )
                    if zip_path:
                        logger.info(
                            f"Created selected seed corpus zip: {zip_path}")
                    else:
                        logger.error(f"nothing to zip")

                return len(paths)

        except Exception as e:
            logger.error(f"Error polling selected seeds: {e}")
            logger.error(traceback.format_exc())
            return 0

    async def poll_seeds_seedgen(
        self,
        task_id: str,
        project_name: str,
        harness_name: str,
        corpus_dir: Path,
        file_manager: FileManager,
    ) -> int:
        """Fetch and extract seedgen corpus to target directory.

        Returns:
            int: Number of files copied, 0 if error or no files
        """
        try:
            # Get latest seedgen path from DB

            seedgen_path = await self.db_manager.get_latest_seeds_seedgen(
                task_id, harness_name
            )
            if not seedgen_path:
                logger.debug(
                    f"No seedgen corpus found for {task_id}/{harness_name}")
                return 0

            # Create temp directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Extract seedgen archive
                src_path = Path(seedgen_path)
                if not src_path.exists():
                    logger.error(f"Seedgen corpus not found at {seedgen_path}")
                    return 0

                extracted_dir = file_manager.extract_archive(
                    src_path, temp_path)

                # Copy files to corpus directory
                corpus_dir.mkdir(parents=True, exist_ok=True)
                file_count = 0

                if self.merge_on_seedgen:
                    for file in corpus_dir.iterdir():
                        if file.is_file():
                            try:
                                shutil.copy2(file, extracted_dir)
                                file_count += 1
                            except FileNotFoundError:
                                logger.debug(
                                    f"Skipping non-existent file: {file}")
                            except Exception as e:
                                logger.warning(
                                    f"Error copying file {file}: {e}")
                else:
                    file_count = len(list(extracted_dir.glob("*")))

                # Create seed corpus zip
                if file_count > 0:
                    # project_name = corpus_dir.parent.parent.name
                    # "work" / project_name / "corpus" / harness_name
                    oss_fuzz_out = (
                        corpus_dir.parent.parent.parent.parent / "out" / project_name
                    )
                    zip_path = file_manager.create_zip_archive(
                        src_path=extracted_dir,
                        dest_dir=oss_fuzz_out,
                        archive_name=f"{harness_name}_seed_corpus",
                    )
                    if zip_path:
                        logger.info(f"Created seed corpus zip: {zip_path}")
                    else:
                        logger.error(f"nothing to zip")

                return file_count

        except Exception as e:
            logger.error(f"Error polling seedgen corpus: {e}")
            logger.error(traceback.format_exc())
            return 0

    async def _collect_variant_metrics(
        self,
        base_metrics: dict,
        log_dir: Path,
        project_name: str,
        harness_name: str,
        variant_types: list[tuple[str, str]] = [
            ("seedgen", "metrics_seedgen"),
            ("aimerged", "metrics_merged"),
        ],
    ) -> dict:
        """Collect metrics from variant fuzzer logs and merge with base metrics.

        Args:
            base_metrics: Base metrics to extend
            log_dir: Base log directory
            project_name: Name of the project
            harness_name: Name of the fuzzer harness
            variant_types: List of tuples (directory_name, metrics_key)

        Returns:
            dict: Combined metrics dictionary
        """
        metrics = base_metrics.copy()

        for variant_dir, metrics_key in variant_types:
            variant_log = log_dir / variant_dir / \
                f"{project_name}_{harness_name}.log"
            if variant_log.exists():
                variant_metrics = self.metrics_collector.parse_log_file(
                    variant_log)
                if variant_metrics:
                    metrics[metrics_key] = variant_metrics

        return metrics

    async def handle_seedgen_corpus(
        self,
        harness_name: str,
        seedgen_corpus_num: dict,
        task_id: str,
        project_name: str,
        corpus_proj_dir: Path,
        fuzz_tool_path: Path,
        log_dir: Path,
        running_process_key: str,
        file_manager: FileManager,
    ) -> bool:
        """Handle seedgen corpus polling and fuzzer creation.
        expected sequence:
            1. run original oss-fuzz fuzzer
            2. run seedgen fuzzer
            3. merge selected corpus

        Args:
            harness_name: Name of the fuzzer harness
            seedgen_corpus_num: Dict tracking number of seeds per harness
            task_id: Task identifier
            project_name: Name of the project
            corpus_proj_dir: Project corpus directory path
            fuzz_tool_path: Path to fuzzing tool
            log_dir: Directory for logs
            running_process_key: Key identifying running process
            file_manager: FileManager instance

        Returns:
            bool: True if any seeds merged, False otherwise
        """
        if not self.fork_on_seedgen:
            logger.debug("Skip running seedgen seeds")
            return False

        selected_seeds_key = f"{harness_name}_selected"
        num_seeds_seedgen = 0
        num_path_selected = 0

        if seedgen_corpus_num.get(selected_seeds_key, 0) > 1:
            logger.debug(f"Already polled selected seeds for {harness_name}")
            return False

        # use seedgen first and then merge selected seeds
        if seedgen_corpus_num.get(harness_name, 0) != 0:
            num_path_selected = await self.poll_seeds_selected(
                task_id=task_id,
                project_name=project_name,
                harness_name=harness_name,
                corpus_dir=corpus_proj_dir / harness_name,
                file_manager=file_manager,
            )
            # merge
            if num_path_selected > 0:
                seedgen_corpus_num[selected_seeds_key] = num_path_selected
                logger.info(
                    f"Merged {num_path_selected} selected seed archives")
            else:
                logger.debug(
                    f"No selected seeds found for {harness_name}, skipping merge")
        else:
            num_seeds_seedgen = await self.poll_seeds_seedgen(
                task_id=task_id,
                project_name=project_name,
                harness_name=harness_name,
                corpus_dir=corpus_proj_dir / harness_name,
                file_manager=file_manager,
            )

        if num_seeds_seedgen > 0:
            seedgen_corpus_num[harness_name] = num_seeds_seedgen
            logger.info(
                f"Polled {num_seeds_seedgen} seed files for {harness_name}")

            proc_info = await self.get_process_info(running_process_key)
            logger.info(f"current helper status: {proc_info}")
            logger.debug(f"Project corpus directory: {corpus_proj_dir}")
            seed_corpus_dir = corpus_proj_dir / "seedgen" / harness_name
            logger.debug(
                f"Creating seedgen corpus directory: {seed_corpus_dir}")
            seed_corpus_dir.mkdir(parents=True, exist_ok=True)
            seed_log_dir = log_dir / "seedgen"
        # new merged seeds
        elif num_path_selected > 1:
            logger.debug(f"No seedgen corpus found for {harness_name}")
            seed_corpus_dir = corpus_proj_dir / "aimerged" / harness_name
            seed_corpus_dir.mkdir(parents=True, exist_ok=True)
            seed_log_dir = log_dir / "aimerged"
        else:
            return False

        asyncio.create_task(
            self.run_single_fuzzer(
                target=harness_name,
                helper_script=fuzz_tool_path / "infra/helper.py",
                corpus_dir=seed_corpus_dir,
                log_dir=seed_log_dir,
                project_name=project_name,
                semaphore=asyncio.Semaphore(1),
                fuzz_tool_path=fuzz_tool_path,
            )
        )

        logger.info(f"Started new fuzzer for {harness_name} with seedgen")
        return True

    async def monitor_fuzzing_metrics(
        self, project_name: str, task_id: str, fuzz_tool_path: Path
    ):
        """
        Monitors fuzzing metrics and stores them in the remote DB.
        (pending migrate to a separate module)
        Args:
            project_name (str): The name of the project being fuzzed.
            task_id (str): The identifier of the fuzzing task.
            fuzz_tool_path (Path): The path to the fuzzing tool's directory.
        Raises:
            Exception: If an error occurs while monitoring fuzzing metrics.
        This function
            1. continuously monitors the log files
            2. tar the seed corpus and store it in the
                 /tmp/corpus_archive/prime/$project/${harness_name}_{round_num}.tar.gz
            3. insert the new metrics to the remote DB
            4. perform the crash triage and store the results in the DB
        """
        # set_task_context(task_id=task_id, project=project_name)
        log_dir = fuzz_tool_path / "logs"
        oss_proj_work_dir = fuzz_tool_path / "build" / "work" / project_name
        corpus_proj_dir = oss_proj_work_dir / "corpus"
        seedgen_corpus_num = {}
        corpus_archive_dir = (
            Path(f"{self.crs_dir}/corpus_archive/prime") /
            task_id / project_name
        )
        crash_backup_dir = (
            Path(f"{self.crs_dir}/crash_backup/prime") / task_id / project_name
        )
        file_manager = FileManager()
        round_num = 0
        processed_crashes = set()
        is_jvm = is_jvm_project(fuzz_tool_path, project_name)
        is_restart_required = False
        redis_client = RedisMiddleware()

        crash_backup_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(__name__)
        set_task_context(task_id=task_id, project=project_name)

        while True:
            try:
                if await self.check_global_task_status(
                    task_id
                ) or await self.check_exit_file(fuzz_tool_path, task_id):
                    break

                logger.debug(
                    f"Monitoring fuzzing metrics at round {round_num}, fuzztool_path: {fuzz_tool_path}")

                for log_file in log_dir.glob(f"{project_name}_*.log"):
                    harness_name = log_file.stem.replace(
                        f"{project_name}_", "", 1)
                    logger.debug(
                        f"Get metrics from log: {log_file}"
                    )
                    metrics = self.metrics_collector.parse_log_file(log_file)
                    running_process_key = f"{task_id}_{project_name}_{harness_name}"
                    ignore_timeout = is_timeout_handled_libfuzzer(
                        fuzz_tool_path, project_name, harness_name)

                    metrics = await self._collect_variant_metrics(
                        base_metrics=metrics,
                        log_dir=log_dir,
                        project_name=project_name,
                        harness_name=harness_name,
                    )

                    if not len(metrics):
                        logger.info(
                            f"[Loop num {round_num}] no metrics info, {harness_name} may has stopped or just started (it should be fine during the 1st loop).")
                    else:
                        # log to remote telemetry
                        task_metadata = redis_client.get_task_metadata(
                            task_id=task_id)
                        try:
                            metrics["metadata"] = (
                                json.loads(
                                    task_metadata) if task_metadata else {}
                            )
                            logger.debug(
                                f"Task metadata for {task_id}: {metrics['metadata']}"
                            )
                        except json.JSONDecodeError:
                            logger.error(
                                f"Failed to decode task metadata for {task_id}: {task_metadata}"
                            )
                        # telemetry
                        log_action_from_metrics(
                            metrics=metrics,
                            round_id=str(round_num),
                            task_id=task_id,
                            harness_name=harness_name,
                            extra_info="independent_events",
                        )

                        logger.info(
                            f"Harness [{harness_name}], {metrics}\nCheck round :{round_num}\n"
                        )

                    # ** Create corpus archive if enabled **
                    if os.getenv("ENABLE_SEED_ARCHIVE"):
                        seed_archive_path = file_manager.create_corpus_archive(
                            corpus_dir=corpus_proj_dir / harness_name,
                            corpus_archive_dir=corpus_archive_dir,
                            harness_name=harness_name,
                            round_num=round_num,
                        )

                        # ** Store seed metrics in DB **
                        # skip the first round
                        if round_num > 1 and seed_archive_path:
                            async with DBManager() as dbm:
                                await dbm.store_metrics(
                                    task_id=task_id,
                                    harness_name=harness_name,
                                    path=str(seed_archive_path.absolute()),
                                    metrics=metrics,
                                )

                    # ** Store seed metrics in Redis **
                    if await redis_client.append_task_metrics(
                        task_id=task_id, metrics=metrics
                    ):
                        logger.debug("Metrics stored in Redis.")

                    # ** Perform crash triage **
                    artifact_path_host = (
                        fuzz_tool_path
                        / "build"
                        / "out"
                        / project_name
                        / "artifacts"
                        / harness_name
                    )

                    existing_crashes_num = len(processed_crashes)
                    # Process all crash files
                    logger.debug(
                        f"Trying to find crash files under {artifact_path_host}")
                    for crash_file in artifact_path_host.glob("crash-*"):
                        total_crashes_num, to_restart = await self.process_crash_file(
                            crash_file=crash_file,
                            processed_crashes=processed_crashes,
                            crash_backup_dir=crash_backup_dir,
                            fuzz_tool_path=fuzz_tool_path,
                            project_name=project_name,
                            harness_name=harness_name,
                            task_id=task_id,
                            file_manager=file_manager,
                            is_jvm=is_jvm,
                            log_file=log_file,
                        )
                        is_restart_required = is_restart_required or to_restart
                        logger.debug(
                            f"Processed crash file: {crash_file.name}")

                        # Check for early cancellation
                        if await self.check_global_task_status(task_id):
                            logger.info(
                                f"[CANCEL] crashes num for {harness_name} : {total_crashes_num}"
                            )
                            raise EarlyCancelledTaskError(
                                f"Task {task_id} was cancelled during crash processing.",
                                {"reason": "task_cancelled_during_triage"},
                            )

                    # Sample one OOM file if any exists
                    oom_file = next(artifact_path_host.glob("oom-*"), None)
                    # just sample twice
                    if oom_file and round_num < 2:
                        total_crashes_num, to_restart = await self.process_crash_file(
                            crash_file=oom_file,
                            processed_crashes=processed_crashes,
                            crash_backup_dir=crash_backup_dir,
                            fuzz_tool_path=fuzz_tool_path,
                            project_name=project_name,
                            harness_name=harness_name,
                            task_id=task_id,
                            file_manager=file_manager,
                            is_jvm=is_jvm,
                            log_file=log_file,
                        )
                        is_restart_required = is_restart_required or to_restart
                        logger.info(f"Processed OOM file: {oom_file.name}")

                    # Sample one timeout file if any exists
                    timeout_file = next(
                        artifact_path_host.glob("timeout-*"), None)
                    # only sample timeout or oom files in the first 10 rounds
                    if (not ignore_timeout) and timeout_file and round_num < 5:
                        total_crashes_num, to_restart = await self.process_crash_file(
                            crash_file=timeout_file,
                            processed_crashes=processed_crashes,
                            crash_backup_dir=crash_backup_dir,
                            fuzz_tool_path=fuzz_tool_path,
                            project_name=project_name,
                            harness_name=harness_name,
                            task_id=task_id,
                            file_manager=file_manager,
                            is_jvm=is_jvm,
                            log_file=log_file,
                        )
                        is_restart_required = is_restart_required or to_restart
                        logger.info(
                            f"Processed timeout file: {timeout_file.name}")

                    # **restart Jazzer with dedup logic**
                    if (
                        is_jvm
                        and len(self.dedup_tokens) > 0
                        and len(processed_crashes) > existing_crashes_num
                    ) or is_restart_required:
                        ignore_tokens = get_ignore_tokens(self.dedup_tokens)
                        if ignore_tokens:
                            logger.info(
                                f"Jazzer will restart with --ignore={ignore_tokens}"
                            )
                        else:
                            logger.info(
                                "Restarting without deduplication. (timeout/oom) "
                            )
                        await self.restart_fuzzer(
                            helper_script=fuzz_tool_path / "infra/helper.py",
                            task_id=task_id,
                            project_name=project_name,
                            corpus_dir=corpus_proj_dir.absolute(),
                            log_dir=log_dir,
                            target=harness_name,
                            file_manager=file_manager,
                            jazzer_args=(
                                f"--ignore={ignore_tokens}"
                                if len(ignore_tokens) > 0
                                else None
                            ),
                            enable_fork=False,
                        )

                    # if os.getenv("DIRECTED_MODE"):
                    #     # skip seedgen & restart if in directed mode
                    #     continue

                    # **poll seedgen corpus**
                    seedgen_res = await self.handle_seedgen_corpus(
                        harness_name=harness_name,
                        seedgen_corpus_num=seedgen_corpus_num,
                        task_id=task_id,
                        project_name=project_name,
                        corpus_proj_dir=corpus_proj_dir,
                        fuzz_tool_path=fuzz_tool_path,
                        log_dir=log_dir,
                        running_process_key=running_process_key,
                        file_manager=file_manager,
                    )

                round_num += 1
                # Check every minute
                await asyncio.sleep(self.monitor_interval)

            except EarlyCancelledTaskError as e:
                logger.info(f"Task {task_id} was cancelled: {e}.")
                break

            except Exception as e:
                logger.error(f"Error monitoring fuzzing metrics: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(self.monitor_interval)

    async def run_command(
        self, cmd: List[str], cwd: Path = None, env: Dict[str, str] = None
    ) -> bytes:
        process_env = os.environ.copy()
        # Remove all environment variables starting with OTEL*
        process_env = {k: v for k, v in process_env.items()
                       if not k.startswith('OTEL')}

        if env:
            process_env.update(env)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=process_env,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            print(stderr)
            raise RuntimeError(f"Command failed")

        return stdout

    async def run_command_with_status(
        self, cmd: List[str], cwd: Path = None, env: Dict[str, str] = None
    ) -> tuple[int, bytes, bytes]:
        """Run a command and return exit code, stdout, and stderr.

        Args:
            cmd: Command to run with arguments
            cwd: Working directory for the command
            env: Environment variables to set for the command (optional)

        Returns:
            tuple: (exit_code, stdout, stderr)
        """
        process_env = os.environ.copy()
        process_env = {k: v for k, v in process_env.items()
                       if not k.startswith('OTEL')}

        if env:
            process_env.update(env)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=process_env,
        )
        stdout, stderr = await process.communicate()

        return process.returncode, stdout, stderr

    async def run_command_with_retry(
        self,
        cmd: List[str],
        cwd: Path = None,
        max_retries: int = 3,
        retry_delay: int = 5,
        env: Dict[str, str] = None,
    ) -> tuple[int, bytes, bytes]:
        """Run a command with retry logic if it fails.

        Args:
            cmd: Command to run with arguments
            cwd: Working directory for the command
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            env: Environment variables to set for the command (optional)

        Returns:
            tuple: (exit_code, stdout, stderr) from the last attempt
        """
        attempts = 0
        last_result = None

        while attempts <= max_retries:
            exit_code, stdout, stderr = await self.run_command_with_status(
                cmd, cwd, env
            )
            last_result = (exit_code, stdout, stderr)

            if exit_code == 0:
                return last_result

            attempts += 1
            if attempts <= max_retries:
                logger.warning(
                    f"Command failed (attempt {attempts}/{max_retries}), "
                    f"retrying in {retry_delay} seconds: {' '.join(cmd)}"
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.warning(
                    f"Command failed after {max_retries} retries: {' '.join(cmd)}"
                )

        return last_result

    async def run_single_fuzzer(
        self,
        target: str,
        helper_script: Path,
        corpus_dir: Path,
        log_dir: Path,
        project_name: str,
        semaphore: asyncio.Semaphore,
        jazzer_args: str = None,
        fuzzer_args_at_env: str = "FUZZER_ARGS=",
        enable_fork: bool = True,
        fuzz_tool_path: Path = None,
    ) -> None:
        """
        the final fuzzer process
        """
        if fuzz_tool_path is None:
            fuzz_tool_path = self.oss_fuzz_path

        async with semaphore:
            logger.info(f"Running fuzzer: {target}")
            target_corpus_dir = corpus_dir / target
            target_corpus_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{project_name}_{target}.log"

            tmp_artifacts_dir = f"/out/artifacts/{target}/"
            # get uuid form oss_path
            taskid_name = fuzz_tool_path.parent.name
            artifact_path_host = (
                fuzz_tool_path / "build" / "out" / project_name / "artifacts" / target
            )
            artifact_path_host.mkdir(parents=True, exist_ok=True)

            fuzzer_args = (
                [
                    "-rss_limit_mb=4096",
                    "-detect_leaks=0",
                    "-timeout=10",
                    "-fork=2",
                    "-use_value_profile=1",
                    "-ignore_ooms=1",
                    "-ignore_timeouts=1",
                    "-ignore_crashes=1",
                    "-create_missing_dirs=1",
                    f"-artifact_prefix={tmp_artifacts_dir}",
                ]
                if enable_fork
                else [
                    "-rss_limit_mb=4096",
                    "-detect_leaks=0",
                    "-timeout=20",
                    "-use_value_profile=1",
                    "-create_missing_dirs=1",
                    f"-artifact_prefix={tmp_artifacts_dir}",
                ]
            )

            dict_file = fuzz_tool_path / "build" / \
                "out" / project_name / f"{target}.dict"
            if dict_file.exists():
                logger.info(
                    f"Found dictionary file: {target}.dict")
                # fuzzer_args.append(f"-dict=/out/{target}.dict")

            # jazzer's args should be placed at the beginning
            if not (jazzer_args is None):
                # e.g. --keep_going=2 --ignore=efcff39c4a9bfc68,04e10ac5f4792b8e
                fuzzer_args.insert(0, jazzer_args)

            cmd = [
                str(helper_script),
                "run_fuzzer",
                "--corpus-dir",
                str(target_corpus_dir),
                "-e",
                fuzzer_args_at_env,
                project_name,
                target,
                " ".join(fuzzer_args),
            ]

            task_target_key = await self._check_running_task(
                taskid_name, project_name, target
            )
            if task_target_key is None:
                return

            env = os.environ.copy()
            env = {k: v for k, v in env.items() if not k.startswith('OTEL')}
            env["OSS_FUZZ_SAVE_CONTAINERS_NAME"] = task_target_key
            # check best docker host for each target
            docker_hosts = get_available_dind_hosts()
            selected_host = get_lowest_cpu_docker_host(docker_hosts)
            if selected_host:
                env["DOCKER_HOST"] = selected_host
            else:
                docker_prune()

            if not docker_prune(docker_host=selected_host):
                logger.warning("Failed to prune docker containers")

            # run docker stop $task_target_key

            logger.debug(f"Running fuzzer command:\n {' '.join(cmd)}\n")
            with open(log_file, "w", encoding="utf-8", errors="replace") as f:
                process = subprocess.Popen(
                    cmd,
                    cwd=fuzz_tool_path,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
            # Store process for later management
            self.running_processes[task_target_key] = process

    async def get_fuzz_targets(
        self, project_name: str, fuzz_tool_path: Path = None
    ) -> List[str]:
        # The fuzz targets are typically in the /out directory
        out_dir = (
            self.oss_fuzz_path / "build" / "out" / project_name
            if fuzz_tool_path is None
            else fuzz_tool_path / "build" / "out" / project_name
        )

        if not out_dir.exists():
            raise RuntimeError(f"Output directory not found: {out_dir}")

        targets = find_fuzz_targets(str(out_dir))
        # Convert full paths to just target names
        return [Path(target).name for target in targets]

    async def run_workflow(
        self, project_name: str, src_path: Path, task_id: str, slicing_res: str = ""
    ) -> None:
        set_task_context(task_id=task_id, project=project_name)
        helper_script = self.oss_fuzz_path / "infra" / "helper.py"
        local_helper_script = self.local_fuzz_tool_path / "infra" / "helper.py"
        redis_client = RedisMiddleware()
        env_docker = None

        # log_action(
        #     "building",
        #     "service_is_up",
        #     {"team.id": "b3yond", "task.id": task_id, "round.id": "final"},
        # )
        # check for available docker hosts
        docker_hosts = get_available_dind_hosts()
        # selected_host = get_lowest_cpu_docker_host(docker_hosts)

        # sanitizers to be enabled
        self.sanitizers = get_sanitizers(
            self.local_fuzz_tool_path, project_name) or ["address"]
        logger.info(
            f"Sanitizers for {project_name}: {self.sanitizers}"
        )

        # log_action(
        #     "building",
        #     "pick_up_docker_hosts",
        #     {"team.id": "b3yond", "task.id": task_id, "round.id": "final"},
        # )
        # Build images on remote dind
        logger.debug(f"DIND: Building image for project {project_name}")
        # do not build fuzzers for each dind by default
        # NOTE: we only need the image to run fuzzing: ghcr.io/aixcc-finals/base-runner
        if self.build_for_all_dind:
            for docker_host in docker_hosts:
                env_docker = {}
                env_docker["DOCKER_HOST"] = docker_host
                image_id = get_docker_image_id(
                    project_name=project_name, docker_host=docker_host)
                if image_id:
                    logger.info(
                        f"Image {image_id} already exists on {docker_host}")
                    continue

                await self.run_command(
                    [str(helper_script), "build_image", "--pull", project_name],
                    cwd=self.oss_fuzz_path,
                    env=env_docker,
                )
        # Build images on host
        logger.info(f"HOST: Building image for project {project_name}")
        await self.run_command(
            [str(helper_script), "build_image", "--no-pull", project_name],
            cwd=self.oss_fuzz_path,
        )

        # Build fuzzers on host at shared oss-fuzz path
        logger.info(f"Building fuzzers: {project_name}")
        build_ret_code, out_msg, err_msg = await self.run_command_with_retry(
            [
                str(helper_script),
                "build_fuzzers",
                "--clean",
                project_name,
                str(src_path.absolute()),
            ],
            cwd=self.oss_fuzz_path,
            # env={"DOCKER_HOST": selected_host} if selected_host else None,
            env=None,
        )

        if build_ret_code != 0:
            logger.warning(f"Build failed for project: {project_name}.")
            # fall back to local build
            build_ret_code, out_msg, err_msg = await self.run_command_with_retry(
                [
                    str(local_helper_script),
                    "build_fuzzers",
                    "--clean",
                    project_name,
                    str(src_path.absolute()),
                ],
                cwd=self.local_fuzz_tool_path,
                # env={"DOCKER_HOST": selected_host} if selected_host else None,
                env=None,
            )

            # NOTE: the cmd is for local build, to be optimized later
            if build_ret_code != 0:
                # log_action(
                #     "building",
                #     "compile_source_code_failed",
                #     {"team.id": "b3yond", "task.id": task_id, "round.id": "final"},
                # )
                raise RuntimeError(f"Build failed: {err_msg}")
            else:
                local_file_manager = FileManager()
                if local_file_manager.sync_directories(
                        src_path=self.oss_fuzz_path / "build" / "out" / project_name,
                        dest_path=self.local_fuzz_tool_path / "build" / "out" / project_name,):
                    logger.info(
                        f"Build completed successfully for project: {project_name} (local build)"
                    )

        # Check build, no need to run in dind
        logger.info(f"Checking build: {project_name}")
        ret_code, out_msg, err_msg = await self.run_command_with_status(
            [str(helper_script), "check_build", project_name],
            cwd=self.oss_fuzz_path,
        )
        ingored_targets = []
        if ret_code != 0:
            ingored_targets = get_failed_check_build_targets(out_msg + err_msg)
        # report to telemetry
        logger.debug(
            f"Build completed for project: {project_name}, logged to telemetry."
        )
        log_action(
            "building",
            "compile_source_code",
            {"team.id": "b3yond", "task.id": task_id, "round.id": "final"},
        )

        # Backup source code and build artifacts
        logger.debug(
            f"Backing up source and build artifacts for fuzzing: {project_name}"
        )
        artifact_backup_fuzz = ArtifactBackup(
            src_path=src_path.parent, oss_fuzz_path=self.oss_fuzz_path
        )

        if not os.getenv("DIRECTED_MODE"):
            backup_result = await artifact_backup_fuzz.backup_artifacts(project_name)
            if backup_result["status"] == "success":
                logger.info(
                    f"Artifacts backed up to: {backup_result.get('backup_path')}")
                # log_action(
                #     "building",
                #     "backup_source_code",
                #     {"team.id": "b3yond", "task.id": task_id, "round.id": "final"},
                # )
                await redis_client.record_public_backup(
                    task_id=task_id, payload=backup_result
                )
            else:
                logger.error(
                    f"Failed to backup artifacts: {backup_result.get('error', 'Unknown error')}"
                )
                # log_action(
                #     "building",
                #     "backup_source_code_failed",
                #     {"team.id": "b3yond", "task.id": task_id, "round.id": "final"},
                # )
        else:
            logger.info(
                f"Skipping target backup for directed mode: {project_name}")

        is_jvm = is_jvm_project(self.oss_fuzz_path, project_name)
        # try to generate dict
        artifact_path = self.oss_fuzz_path / "build" / "out" / project_name
        # Filter out targets that failed during build check
        targets = await self.get_fuzz_targets(project_name)
        if is_jvm:
            logger.info("Generating dictionaries statically.")
            try:
                gen_dict_java(artifact_path=str(artifact_path),
                              output_dir=str(artifact_path),
                              harnesses=targets)
            except Exception as e:
                logger.error(f"Error generating dict: {e}")
        # Run fuzzers
        if len(ingored_targets) > 0:
            logger.info(
                f"Removing failed targets: {', '.join(ingored_targets)}")
            targets = [t for t in targets if t not in ingored_targets]

        if not targets:
            logger.warning(
                f"No valid fuzz targets found for project: {project_name}")
            raise RuntimeError("No valid fuzz targets found")

        # NOTE: the oss-fuzz should be shared among all dind hosts
        log_dir = self.oss_fuzz_path / "logs"
        log_dir.mkdir(exist_ok=True)

        # Create corpus directory
        corpus_dir = self.oss_fuzz_path / "build" / "work" / project_name / "corpus"
        for target in targets:
            corpus_dir.mkdir(parents=True, exist_ok=True)
            create_a_simple_seed_corpus(corpus_dir / target)

        if not docker_prune():
            logger.warning("Failed to prune docker containers")

        enable_fork = not is_jvm

        # Create semaphore to limit concurrent processes
        semaphore = asyncio.Semaphore(self.max_workers)

        # Create and run tasks
        tasks = []
        for target in targets:
            fuzzer_args = get_slicing_extra_args(slicing_res, target)
            ignore_timeout = is_timeout_handled_libfuzzer(
                self.oss_fuzz_path, project_name, target)
            if ignore_timeout:
                logger.debug(
                    f" [NEW FEAT] Timeout is handled in libfuzzer options for {target}.")
            enable_fork = enable_fork or ignore_timeout

            # Skip targets with no slicing results in directed mode
            if (
                os.getenv("DIRECTED_MODE")
                and fuzzer_args.strip() == self.default_fuzzer_args_env
            ):
                logger.info(
                    f"Skipping target {target} in directed mode as it has no slicing result"
                )
                continue

            tasks.append(
                self.run_single_fuzzer(
                    target,
                    helper_script,
                    corpus_dir.absolute(),
                    log_dir,
                    project_name,
                    semaphore,
                    None,
                    fuzzer_args_at_env=fuzzer_args,
                    enable_fork=enable_fork,
                )
            )

        # Start metrics monitoring by task_id
        self.monitoring_task[task_id] = asyncio.create_task(
            self.monitor_fuzzing_metrics(
                project_name, task_id, copy.copy(self.oss_fuzz_path)
            )
        )

        await asyncio.gather(*tasks)

        logger.info(
            f"All fuzzers started - {project_name}: {'|'.join(targets)}")
