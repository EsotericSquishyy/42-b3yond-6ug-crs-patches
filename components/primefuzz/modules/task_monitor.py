import logging
import asyncio
from pathlib import Path
import shutil
import tempfile
from typing import Dict
from modules.metrics_collector import MetricsCollector
from modules.file_manager import FileManager
from db.db_manager import DBManager
from modules.triage import CrashTriager

logger = logging.getLogger(__name__)


class TaskMonitor:
    def __init__(
        self,
        db_manager: DBManager,
        file_manager: FileManager,
        metrics_collector: MetricsCollector,
        monitor_interval: int = 60,
        exit_key: str = "STOP_NOW",
        callback_stop: callable = None,
        callback_run_single_fuzzer: callable = None,
    ):
        self.db_manager = db_manager
        self.file_manager = file_manager
        self.metrics_collector = metrics_collector
        self.monitor_interval = monitor_interval
        self.exit_key = exit_key
        self.stop_all_fuzzers = callback_stop
        self.run_single_fuzzer = callback_run_single_fuzzer

    async def check_exit_file(self, fuzz_tool_path: Path, task_id: str) -> bool:
        """Check if exit file exists and handle stopping.

        Returns:
            bool: True if monitoring should stop, False to continue
        """
        exit_file = fuzz_tool_path / self.exit_key
        logger.debug(f"Checking for exit file: {exit_file.absolute()}")

        if exit_file.exists():
            logger.info(f"Exit file found, stopping fuzzers for task {task_id}")
            if self.stop_all_fuzzers is not None:
                stopped = await self.stop_all_fuzzers("", task_id)
                if stopped:
                    exit_file.unlink()
                    logger.info(
                        f"Fuzzers stopped for task {task_id}, monitor task exiting"
                    )
                    return True
        return False

    async def poll_seeds_seedgen(
        self, task_id: str, project_name: str, harness_name: str, fuzz_tool_path: Path
    ) -> int:
        """Fetch and extract seedgen corpus to target directory."""
        try:
            seedgen_path = await self.db_manager.get_latest_seeds_seedgen(
                task_id, harness_name
            )
            if not seedgen_path:
                return 0

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                src_path = Path(seedgen_path)

                if not src_path.exists():
                    logger.error(f"Seedgen corpus not found at {seedgen_path}")
                    return 0

                extracted_dir = self.file_manager.extract_archive(src_path, temp_path)

                file_count = 0
                for file in extracted_dir.iterdir():
                    if file.is_file():
                        # shutil.copy2(file, corpus_dir)
                        file_count += 1

                # Create seed corpus zip
                if file_count > 0:
                    oss_fuzz_out = fuzz_tool_path / "build" / "out" / project_name
                    zip_path = self.file_manager.create_zip_archive(
                        src_path=extracted_dir,
                        dest_dir=oss_fuzz_out,
                        archive_name=f"{harness_name}_seed_corpus",
                    )
                    logger.info(f"Created seed corpus zip: {zip_path}")

                return file_count

        except Exception as e:
            logger.error(f"Error polling seedgen corpus: {e}")
            return 0

    async def _process_crash_files(
        self,
        crash_backup_dir: Path,
        processed_crashes: set,
        project_name: str,
        harness_name: str,
        task_id: str,
        fuzz_tool_path: Path,
    ) -> set:
        """Process crash files and perform triage.

        Args:
            crash_backup_dir: Directory to backup crash files
            processed_crashes: Set of already processed crash files
            project_name: Name of the project
            harness_name: Name of the fuzzer harness
            task_id: Task identifier
            fuzz_tool_path: Path to OSS-Fuzz tools
        """
        artifact_path = (
            fuzz_tool_path / "build" / "out" / project_name / "artifacts" / harness_name
        )

        for crash_file in artifact_path.glob("crash-*"):
            if crash_file.name in processed_crashes:
                continue

            processed_crashes.add(crash_file.name)
            copied_crash_file = self.file_manager.copy_file(
                crash_file, crash_backup_dir
            )

            if copied_crash_file is None:
                continue

            triager = CrashTriager(fuzz_tool_path)
            crash_info = await triager.triage_crash(
                project_name, harness_name, copied_crash_file
            )
            logger.info(f"Triage:\t{crash_file.name}, Bug type:\t{crash_info.bug_type}")

            await self.db_manager.store_bug_profile_info(task_id, crash_info)

        return processed_crashes

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
        log_dir = fuzz_tool_path / "logs"
        oss_proj_work_dir = fuzz_tool_path / "build" / "work" / project_name
        corpus_proj_dir = oss_proj_work_dir / "corpus"
        seedgen_corpus_num = {}
        corpus_archive_dir = (
            Path(f"{self.crs_dir}/corpus_archive/prime") / task_id / project_name
        )
        crash_backup_dir = (
            Path(f"{self.crs_dir}/crash_backup/prime") / task_id / project_name
        )
        round_num = 0
        processed_crashes = set()

        crash_backup_dir.mkdir(parents=True, exist_ok=True)

        while True:
            try:
                if await self.check_exit_file(fuzz_tool_path, task_id):
                    break

                for log_file in log_dir.glob(f"{project_name}_*.log"):
                    harness_name = log_file.stem.replace(f"{project_name}_", "", 1)
                    metrics = self.metrics_collector.parse_log_file(log_file)
                    running_process_key = f"{task_id}_{project_name}_{harness_name}"

                    if metrics:
                        logger.info(
                            f"Metrics parsed for {harness_name}, up time :{metrics.get('time_seconds')}\n"
                        )

                        # ** Create corpus archive **
                        archive_path = self.file_manager.create_corpus_archive(
                            corpus_dir=corpus_proj_dir / harness_name,
                            corpus_archive_dir=corpus_archive_dir,
                            harness_name=harness_name,
                            round_num=round_num,
                        )

                        await self.db_manager.store_metrics(
                            task_id=task_id,
                            harness_name=harness_name,
                            path=str(archive_path.absolute()),
                            metrics=metrics,
                        )

                        # ** Perform crash triage **
                        processed_crashes = await self._process_crash_files(
                            crash_backup_dir=crash_backup_dir,
                            processed_crashes=processed_crashes,
                            project_name=project_name,
                            harness_name=harness_name,
                            task_id=task_id,
                            fuzz_tool_path=fuzz_tool_path,
                        )

                        # **poll seedgen corpus**
                        if seedgen_corpus_num.get(harness_name, 0) != 0:
                            logger.debug("continue to poll seedgen corpus")
                            break

                        # existing seedgen logic
                        num_seeds = await self.poll_seeds_seedgen(
                            task_id=task_id,
                            project_name=project_name,
                            harness_name=harness_name,
                            fuzz_tool_path=fuzz_tool_path,
                        )
                        if num_seeds > 0:
                            seedgen_corpus_num[harness_name] = num_seeds
                            logger.info(
                                f"Polled {num_seeds} seed files for {harness_name} to {corpus_proj_dir}"
                            )
                            proc_info = await self.get_process_info(running_process_key)
                            logger.info(f"current fuzzers status: {proc_info}")
                            seedgen_corpus_dir = corpus_proj_dir / "seedgen"
                            seedgen_corpus_dir.mkdir(parents=True, exist_ok=True)
                            seedgen_log_dir = log_dir / "seedgen"
                            # Stop existing fuzzer (no needed for now)
                            # await self.stop_all_fuzzers(running_process_key, None)
                            if not self.fork_on_seedgen:
                                continue

                            if self.run_single_fuzzer is None:
                                continue

                            asyncio.create_task(
                                self.run_single_fuzzer(
                                    target=harness_name,
                                    helper_script=fuzz_tool_path / "infra/helper.py",
                                    corpus_dir=seedgen_corpus_dir,
                                    log_dir=seedgen_log_dir,
                                    project_name=project_name,
                                    semaphore=asyncio.Semaphore(1),
                                )
                            )
                            logger.info(
                                f"Started new fuzzer for {harness_name} with seedgen"
                            )

                round_num += 1
                # Check every minute
                await asyncio.sleep(self.monitor_interval)

            except Exception as e:
                logger.error(f"Error monitoring fuzzing metrics: {e}")
                await asyncio.sleep(self.monitor_interval)
