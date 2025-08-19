import os
import logging
import re
import subprocess
from pathlib import Path

import docker
from daemon.modules.crash_handler import CrashHandler
from daemon.modules.workspace import WorkspaceManager
from daemon.modules.seed_syncer import SeedSyncer
from daemon.modules.telemetry import log_telemetry_action
from utils.docker_utils import _env_to_docker_args, docker_run_background
from daemon.directed_msg import DirectedMsg
from utils.target_utils import find_fuzz_targets
from utils.misc import safe_extract_tar
from utils.misc import wait_for_path

import tarfile
from db.db import DBConnection
from db.models.fuzz_related import Seed

from sqlalchemy import select

class FuzzerRunner:
    def __init__(self, directed_msg: DirectedMsg, workspace_manager: WorkspaceManager,
                 base_runner_image: str = 'ghcr.io/aixcc-finals/base-runner:v1.3.0',
                 image_prefix: str = 'aixcc-afc/oss-fuzz'):
        """
        Initializes FuzzerRunner with data from DirectedMsg and the WorkspaceManager.

        Args:
            directed_msg (DirectedMsg): Contains task and project details.
            workspace_manager (WorkspaceManager): Manages the task workspace.
            base_runner_image (str): Base runner image for fuzzing containers.
            image_prefix (str): Prefix for the project-specific Docker image.
        """
        self.directed_msg = directed_msg
        self.project_name = directed_msg.project_name
        self.task_id = directed_msg.task_id
        self.workspace_manager = workspace_manager
        self.slave_num = 0
        self.base_runner_image = base_runner_image
        self.image_name = f'{image_prefix}/{self.project_name}'

        # Use the workspace provided by WorkspaceManager.
        self.workspace_dir = self.workspace_manager.workspace_dir

        # Retrieve the focused repository from the workspace.
        focused_repo = self.workspace_manager.get_focused_repo()
        if not focused_repo:
            raise ValueError("Focused repository not found in the workspace.")
        self.focused_repo = str(focused_repo)  # Ensure it's a string path.

        # <workspace_dir>/oss-fuzz/infra/helper.py
        self.helper_path = self.workspace_manager.helper_path
        self.dockerfile_path = self.workspace_manager.fuzzing_tooling_path / 'projects' / self.project_name / 'Dockerfile'

        self.docker_client = docker.from_env()
        # The container ID.
        self.container_id = None

        # Store containers and observers for each harness
        self.containers = {}  # harness_name -> container_id
        self.observers = {}   # harness_name -> CrashHandler
        self.syncers = {}     # harness_name -> SeedSyncer

    @property
    def output_dir(self) -> Path:
        """
        Computes and returns the output directory for the fuzzer.
        """
        # This property encapsulates the long output directory path
        return self.helper_path.parent.parent / 'build' / 'out' / self.project_name
    
    def workdir_from_dockerfile(self, fuzz_tooling, project_name):
        WORKDIR_REGEX = re.compile(r'\s*WORKDIR\s*([^\s]+)')
        dockerfile_path = os.path.join(
            fuzz_tooling, "projects", project_name, "Dockerfile")
        with open(dockerfile_path) as file_handle:
            lines = file_handle.readlines()
        for line in reversed(lines):  # reversed to get last WORKDIR.1
            match = re.match(WORKDIR_REGEX, line)
            logging.debug(f"Match: {match}")
            if match:
                workdir = match.group(1)
                workdir = workdir.replace('$SRC', '/src')
                if not os.path.isabs(workdir):
                    workdir = os.path.join('/src', workdir)
                log_telemetry_action(title="Workdir from Dockerfile",msg_list=[f"Workdir: {workdir}"],action_name="workdir_from_dockerfile",status="OK",level="verbose")
                return workdir

        log_telemetry_action(title="Workdir from Dockerfile",msg_list=[f"Workdir: {os.path.join('/src', project_name)}"],action_name="workdir_from_dockerfile",status="ERROR",level="debug")
        return os.path.join('/src', project_name)

    def seedgen_dir(self, harness_name: str) -> Path:
        """
        Computes and returns the seedgen directory for the fuzzer.
        Args:
            harness_name (str): The name of the harness.
        """
        return self.helper_path.parent.parent / 'build' / 'out' / self.project_name / 'seedgen' / harness_name 

    def prepare(self):
        """
        Prepare the environment by building the Docker image and fuzzers.
        Returns:
            bool: True if preparation is successful, False otherwise.
        """
        if not self._build_docker_image():
            logging.error(f"Failed to build Docker image for project '{self.project_name}'")
            return False
        if not self._build_fuzzers():
            logging.error(f"Failed to build fuzzers for project '{self.project_name}'")
            return False
        return True

    def _build_docker_image(self):
        """
        Checks if the Docker image exists; if not, builds it.
        Returns:
            bool: True if the image exists or was built successfully, False otherwise.
        """
        log_telemetry_action(title="Docker image check",msg_list=[f"Image name: {self.image_name}"],action_name="build_docker_image",status="OK",level="info")
        try:
            self.docker_client.images.get(self.image_name)
            logging.info("Docker image '%s' already exists.", self.image_name)
            log_telemetry_action(title="Docker image check",msg_list=[f"Image name: {self.image_name}"],action_name="build_docker_image",status="OK",level="verbose")
            return True
        except docker.errors.ImageNotFound:
            logging.info("Building Docker image for project '%s'", self.project_name)
            cmd = ['python3', self.helper_path, 'build_image', '--no-pull', self.project_name]
            log_telemetry_action(title="Docker image build",msg_list=[f"Command: {cmd}"],action_name="build_docker_image",status="OK",level="verbose")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logging.error("Error building Docker image: %s", result.stderr)
                log_telemetry_action(title="Docker image build",msg_list=[f"Error: {result.stderr}"],action_name="build_docker_image",status="ERROR",level="debug")
                return False
            return True

    def _build_fuzzers(self):
        """
        Builds fuzzers using the helper script.
        Returns:
            bool: True if fuzzers were built successfully, False otherwise.
        """
        logging.info("Building fuzzers for project '%s'", self.project_name)
        log_telemetry_action(title="Fuzzers build",msg_list=[f"Project name: {self.project_name}"],action_name="build_fuzzers",status="OK",level="info")
        workdir = self.workdir_from_dockerfile(self.workspace_manager.fuzzing_tooling_path, self.project_name)
        cmd = [
            'python3', self.helper_path, 'build_fuzzers',
            '--engine', 'afl',
            '-e', f'AFL_LLVM_ALLOWLIST={workdir}/aixcc_beyond_allowlist.txt',
            '--clean', self.project_name, self.focused_repo
        ]
        log_telemetry_action(title="Building fuzzers",msg_list=[f"Fuzzers: {cmd}"],action_name="build_fuzzers",status="OK",level="verbose")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logging.error("Error building fuzzers: %s", result.stderr)
            log_telemetry_action(title="Building fuzzers",msg_list=[f"Standard output: {result.stdout}"],action_name="build_fuzzers",status="ERROR",level="debug")
            return False
        return True


    def run_fuzzer_with_pid(self, harness_name: str, instance_id: str, harness_args=[], 
                           sanitizer='address', extends_env=None, corpus_dir=None, 
                           architecture='x86_64', master=True, slaves=None):
        """
        Runs a fuzzer (harness) in a Docker container as a detached background process.

        Args:
            harness_name (str): The name of the harness.
            instance_id (str): Unique identifier for this fuzzer instance.
            harness_args (list): Additional arguments for the fuzzer.
            sanitizer (str): Sanitizer type.
            extends_env (list, optional): Additional environment variables.
            corpus_dir (str, optional): Path to the corpus directory.
            architecture (str, optional): Architecture (default 'x86_64').
            master (bool, optional): Whether to run as master.
            slaves (int, optional): Number of slave instances. If None, uses AIXCC_AFL_SLAVE_NUM env var or defaults to 4.

        Returns:
            str: The container ID of the started fuzzer container.
        """
        # Get slave count from environment variable or use default
        if slaves is None:
            slaves = int(os.getenv('AIXCC_AFL_SLAVE_NUM', '4'))

        log_telemetry_action(title="Fuzzer run",msg_list=[f"Harness name: {harness_name}, Instance ID: {instance_id}, Sanitizer: {sanitizer}, Master: {master}, Slaves: {slaves}"],action_name="run_fuzzer_with_pid",status="OK",level="info")
        
        env = [
            'FUZZING_ENGINE=afl',
            f'SANITIZER={sanitizer}',
            'RUN_FUZZER_MODE=interactive',
            'HELPER=True',
        ]
        
        # Use distributed mode to run multiple fuzzers and sync seeds in the future
        afl_fuzzer_args = "--version;echo IyEvYmluL2Jhc2gKCk1BU1RFUj1mYWxzZQpTTEFWRV9TVEFSVD0tMQpTTEFWRV9FTkQ9LTEKTkVXX0FSR1M9KCkKT1VUPSQoZWNobyAiJFBBVEgiIHwgY3V0IC1kOiAtZjEpCgoKd2hpbGUgKCggIiQjIiApKTsgZG8KICBjYXNlICIkMSIgaW4KICAgIC0tbWFzdGVyKQogICAgICBNQVNURVI9dHJ1ZQogICAgICBzaGlmdAogICAgICA7OwogICAgLS1zbGF2ZS1zdGFydCkKICAgICAgU0xBVkVfU1RBUlQ9IiQyIgogICAgICBzaGlmdCAyCiAgICAgIDs7CiAgICAtLXNsYXZlLWVuZCkKICAgICAgU0xBVkVfRU5EPSIkMiIKICAgICAgc2hpZnQgMgogICAgICA7OwogICAgKikKICAgICAgTkVXX0FSR1MrPSgiJDEiKQogICAgICBzaGlmdAogICAgICA7OwogIGVzYWMKZG9uZQoKaWYgWyAiJE1BU1RFUiIgPSB0cnVlIF07IHRoZW4KICBDTUQ9IiRPVVQvYWZsLWZ1enogLU0gbWFzdGVyICR7TkVXX0FSR1NbKl19IgogIGVjaG8gIkV4ZWN1dGluZzogJENNRCIKICAiJE9VVC9hZmwtZnV6eiIgLU0gbWFzdGVyICIke05FV19BUkdTW0BdfSIgJgpmaQoKaWYgW1sgIiRTTEFWRV9TVEFSVCIgLWdlIDAgJiYgIiRTTEFWRV9FTkQiIC1nZSAiJFNMQVZFX1NUQVJUIiBdXTsgdGhlbgogIGZvciAoKCBpPVNMQVZFX1NUQVJUOyBpPD1TTEFWRV9FTkQ7IGkrKyApKTsgZG8KICAgIENNRD0iJE9VVC9hZmwtZnV6eiAtUyBzbGF2ZSRpICR7TkVXX0FSR1NbKl19IgogICAgZWNobyAiRXhlY3V0aW5nOiAkQ01EIgogICAgIiRPVVQvYWZsLWZ1enoiIC1TICJzbGF2ZSRpIiAiJHtORVdfQVJHU1tAXX0iICYKICBkb25lCmZpCgp3YWl0Cg==| base64 -d > /tmp/run_fuzzer_distributed; chmod +x /tmp/run_fuzzer_distributed; /tmp/run_fuzzer_distributed"
        if master:
            afl_fuzzer_args += f" --master"
        if slaves > 0:
            afl_fuzzer_args += f" --slave-start {self.slave_num} --slave-end {self.slave_num + slaves}"
            self.slave_num += slaves
        self.slave_num += 1
        # Add the AFL fuzzer args to env
        env.append(f'AFL_FUZZER_ARGS={afl_fuzzer_args}')
        
        if extends_env:
            env += extends_env

        run_args = _env_to_docker_args(env)

        if corpus_dir:
            if not os.path.exists(corpus_dir):
                logging.error("The path provided in --corpus-dir argument does not exist")
                return False
            corpus_dir = os.path.realpath(corpus_dir)
            run_args.extend([
                '-v',
                '{corpus_dir}:/tmp/{harness}_corpus'.format(
                    corpus_dir=corpus_dir,
                    harness=harness_name
                )
            ])

        output_dir = self.output_dir
        # TODO: Make this more flexible to support other sanitizers
        afl_dir = Path(self.output_dir / f"{harness_name}_afl_address_out")
        if not output_dir.exists():
            logging.error("Fuzzer output directory not found: %s", output_dir)
            raise FileNotFoundError("Fuzzer output directory not found")

        # Create CrashHandler with instance_id
        self.observers[harness_name] = CrashHandler(
            output_dir=afl_dir,
            directed_msg=self.directed_msg,
            harness_name=harness_name,
            instance_id=instance_id
        )
        
        self.syncers[harness_name] = SeedSyncer(
            task_id = self.task_id,
            harness = harness_name,
            output_dir = output_dir,
            interval = 600
        )  
        
        run_args.extend([
            '-v',
            f'{output_dir}:/out',
            '-t',
            self.base_runner_image,
            'run_fuzzer',
            harness_name,
        ] + harness_args)

        # Store container ID
        log_telemetry_action(title="Fuzzer run",msg_list=[f"Run args: {run_args}"],action_name="run_fuzzer_with_pid",status="OK",level="verbose")
        container_id = docker_run_background(run_args, architecture=architecture)
        if not container_id:
            log_telemetry_action(title="Fuzzer run",msg_list=[f"Failed to start fuzzer container"],action_name="run_fuzzer_with_pid",status="ERROR",level="debug")
            raise RuntimeError("Failed to start fuzzer container")
        # Wait for the fuzzer to be started
        wait_for_path(afl_dir)
        self.containers[harness_name] = container_id
        logging.info("Started fuzzer '%s' with container ID: %s", harness_name, container_id)
        log_telemetry_action(title="Fuzzer run",msg_list=[f"Started fuzzer '{harness_name}' with container ID: {container_id}"],action_name="run_fuzzer_with_pid",status="OK",level="verbose")
        return container_id

    def start_observer(self, harness_name: str):
        """
        Starts the CrashHandler observer for a specific harness.

        Args:
            harness_name (str): The name of the harness to start observing.
        """
        log_telemetry_action(title="CrashHandler start",msg_list=[f"Harness name: {harness_name}"],action_name="start_observer",status="OK",level="info")
        if harness_name not in self.observers:
            logging.error(f"CrashHandler not initialized for harness: {harness_name}")
            log_telemetry_action(title="CrashHandler not initialized",msg_list=[f"Harness name: {harness_name}"],action_name="start_observer",status="ERROR",level="debug")
            raise RuntimeError(f"CrashHandler not initialized for harness: {harness_name}")
        
        self.observers[harness_name].start()

    def start_syncer(self, harness_name: str):
        """
        Starts the SeedSyncer for a specific harness.

        Args:
            harness_name (str): The name of the harness to start syncing.
        """
        log_telemetry_action(title="SeedSyncer start",msg_list=[f"Harness name: {harness_name}"],action_name="start_syncer",status="OK",level="info")
        if harness_name not in self.syncers:
            logging.error(f"SeedSyncer not initialized for harness: {harness_name}")
            log_telemetry_action(title="SeedSyncer not initialized",msg_list=[f"Harness name: {harness_name}"],action_name="start_syncer",status="ERROR",level="debug")
            raise RuntimeError(f"SeedSyncer not initialized for harness: {harness_name}")
        
        self.syncers[harness_name].start()

    def stop_fuzzer(self, harness_name: str = None):
        """
        Stops and removes the running fuzzer container(s).

        Args:
            harness_name (str, optional): Specific harness to stop. If None, stops all.
        """
        if harness_name:
            harnesses = [harness_name]
        else:
            harnesses = list(self.containers.keys())
        log_telemetry_action(title="Fuzzer stop",msg_list=[f"Harnesses: {harnesses}"],action_name="stop_fuzzer",status="OK",level="info")
        for harness in harnesses:
            container_id = self.containers.get(harness)
            if container_id:
                logging.info(f"Stopping container for harness {harness}: {container_id}")
                log_telemetry_action(title="Fuzzer stop",msg_list=[f"Stopping container for harness {harness}: {container_id}"],action_name="stop_fuzzer",status="OK",level="verbose")
                stop_result = subprocess.run(
                    ["docker", "stop", container_id],
                    capture_output=True, text=True
                )
                if stop_result.returncode != 0:
                    logging.error(f"Failed to stop container {container_id}: {stop_result.stderr}")
                else:
                    logging.info(f"Container {container_id} stopped.")
                del self.containers[harness]
            
            # Stop the observer if it exists
            if harness in self.observers:
                self.observers[harness].stop()
                del self.observers[harness]
                
            # Stop the syncer if it exists
            if harness in self.syncers:
                self.syncers[harness].stop()
                del self.syncers[harness]

    def detect_fuzz_targets(self):
        """
        Detects and returns all fuzz targets in the output directory.
        
        Returns:
            list[str]: A list of detected fuzz target filenames.
        
        Raises:
            FileNotFoundError: If the fuzzer output directory does not exist.
        """
        if not self.output_dir.exists():
            logging.error("Fuzzer output directory not found: %s", self.output_dir)
            log_telemetry_action(title="Fuzzer output directory not found",msg_list=[f"Output directory: {self.output_dir}"],action_name="detect_fuzz_targets",status="ERROR",level="debug")
            raise FileNotFoundError("Fuzzer output directory not found")
        
        # Call the existing utility function to find fuzz targets.
        fuzz_targets = find_fuzz_targets(str(self.output_dir))
        logging.debug("Detected fuzz targets: %s", fuzz_targets)
        log_telemetry_action(title="Fuzz targets detected",msg_list=[f"Fuzz targets: {fuzz_targets}"],action_name="detect_fuzz_targets",status="OK",level="verbose")
        return fuzz_targets
    
    
    def pull_seeds_seedgen(self, task_id: str, harness_name: str):
        """
        Fetches the latest seedgen corpus for a given task and harness.

        Args:
            task_id (str): Task identifier
            harness_name (str): The name of the harness.
            
        Returns:
            int: The number of files in the seedgen corpus.
        """
        file_count = 0
        # Connect to db
        db_connection = DBConnection(db_url = os.getenv('DATABASE_URL'))
        db_connection.start_session()
        stmt = (
            select(Seed.path)
            .where(Seed.task_id == task_id, Seed.harness_name == harness_name, Seed.fuzzer == 'seedgen')
            .order_by(Seed.created_at.desc())
            .limit(1)
        )
        results = db_connection.execute_stmt_with_session(stmt)
        if not results:
            logging.debug(f"No seedgen found for task_id={task_id}, harness_name={harness_name}")
            log_telemetry_action(title="Seedgen not found",msg_list=[f"Task ID: {task_id}, Harness name: {harness_name}"],action_name="pull_seeds_seedgen",status="OK",level="verbose")
            db_connection.stop_session()
            return file_count
        seedgen_path = results[0]
        src_path = Path(seedgen_path)
        if not src_path.exists():
            logging.error(f"Seedgen corpus not found at {seedgen_path}")
            log_telemetry_action(title="Seedgen corpus not found",msg_list=[f"Seedgen path: {seedgen_path}"],action_name="pull_seeds_seedgen",status="ERROR",level="debug")
            db_connection.stop_session()
            return file_count
        corpus_dir = self.seedgen_dir(harness_name = harness_name)
        corpus_dir.mkdir(parents=True, exist_ok=True)
        if tarfile.is_tarfile(src_path):
            # Extract seedgen archive
            try:
                log_telemetry_action(title="Seedgen corpus extracted",msg_list=[f"Seedgen path: {src_path}"],action_name="pull_seeds_seedgen",status="OK",level="info")
                safe_extract_tar(src_path, corpus_dir)
                file_count = len(list(corpus_dir.glob('*')))
            except Exception as e:
                logging.error(f"Error extracting tarfile {src_path}: {e}")
                db_connection.stop_session()
                raise
        else:
            logging.error(f"Invalid seedgen archive: {src_path}")
        db_connection.stop_session()
        return file_count