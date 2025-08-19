import asyncio
import json
import os
import random
import shutil
import string
import subprocess
import tarfile
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Union

from loguru import logger

# Task context
_task_context = {}


def set_task_context(task_id: str, project: str) -> None:
    """Set the current task context."""
    global _task_context
    _task_context = {"task_id": task_id, "project": project}


def log_action(action: str, event: str, metadata: Dict = None) -> None:
    """Log an action with the given event and metadata."""
    if metadata is None:
        metadata = {}

    log_data = {"action": action, "event": event, **metadata, **_task_context}

    logger.info(json.dumps(log_data))


def extract_archive(file_path: Path, extract_dir: Path) -> Path:
    extract_dir.mkdir(parents=True, exist_ok=True)

    if file_path.suffix in [".tar", ".gz", ".tgz"]:
        with tarfile.open(file_path) as tar:
            # Get first member path with normalization
            first_dir = None
            for member in tar.getmembers():
                if member.isdir():
                    # Normalize path to remove ./ and split
                    normalized_path = os.path.normpath(member.name)
                    first_dir = extract_dir / normalized_path.split("/")[0]
                    if not first_dir.name.startswith("."):
                        break

            # Extract archive
            tar.extractall(path=extract_dir)

            # Return first directory if found
            if (first_dir and first_dir.exists()
                and first_dir.is_dir()
                    and (not first_dir.name.startswith("."))):
                return first_dir
    else:
        # stop the builder here
        raise ValueError(
            f"Unsupported archive format: {file_path.suffix}. Supported formats are .tar, .gz, .tgz"
        )

    return extract_dir


def copy_directory(src_dir_path: Path, dest_dir: Path, dest_name: str = None) -> Optional[Path]:
    """Copy directory to destination with optional renaming.

    Args:
        src_dir_path: Source directory to copy
        dest_dir: Destination parent directory
        dest_name: Optional new name for destination directory

    Returns:
        Path: Path to copied directory, None if error
    """
    try:
        if not src_dir_path.is_dir():
            raise NotADirectoryError(
                f"Source directory not found: {src_dir_path}")

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / \
            (dest_name if dest_name else src_dir_path.name)

        # Remove destination if it exists
        if dest_path.exists():
            logger.info(
                f"Use existing destination directory: {dest_path}")
            return dest_path

        # Copy directory recursively with metadata
        shutil.copytree(src_dir_path, dest_path)
        logger.debug(
            f"Successfully copied directory {src_dir_path} to {dest_path}")
        return dest_path

    except Exception as e:
        logger.error(
            f"Error copying directory {src_dir_path} to {dest_dir}: {e}")
        return None


def get_project_lang(oss_fuzz_path: Path, project_name: str) -> Optional[str]:
    """Get the programming language of the project."""
    yaml_path = oss_fuzz_path / "projects" / project_name / "project.yaml"
    if not yaml_path.exists():
        logger.error(f"project.yaml not found for {project_name}")
        return None

    try:
        with open(yaml_path, "r") as f:
            project_yaml = yaml.safe_load(f)
            language = project_yaml.get("language", "")
            return language
    except Exception as e:
        logger.error(f"Error reading project.yaml: {e}")
        return None

    return None


async def run_command(
    cmd: List[str], cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None
) -> str:
    """Run a command asynchronously and return its output."""
    logger.info(f"Running command: {' '.join(cmd)}")

    # Prepare environment variables
    environment = None
    if env:
        environment = os.environ.copy()
        environment.update(env)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=environment,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        logger.error(f"Command failed with exit code {process.returncode}")
        logger.error(f"stderr: {stderr.decode()}")
        raise RuntimeError(f"Command failed: {cmd}")

    return stdout.decode()


def run_command_sync(
    cmd: List[str], cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None
) -> str:
    """Run a command synchronously and return its output."""
    logger.info(f"Running command: {cmd}")

    # Prepare environment variables
    environment = None
    if env:
        environment = os.environ.copy()
        environment.update(env)

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=environment,
    )

    if result.returncode != 0:
        logger.error(f"Command failed with exit code {result.returncode}")
        logger.error(f"stderr: {result.stderr}")
        raise RuntimeError(f"Command failed: {cmd}")

    return result.stdout


def run_command_sync_no_raise(
    cmd: List[str], cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None,
    timeout: int = 120
) -> tuple[int, str, str]:
    """
    Run a command synchronously and return a tuple with (return_code, stdout, stderr).
    Does not raise an exception if the command fails.
    
    Args:
        cmd: Command to run as a list of strings
        cwd: Current working directory
        env: Environment variables
        timeout: Timeout in seconds (default: 120)
        
    Returns:
        Tuple of (return_code, stdout, stderr). Returns code 127 on timeout.
    """
    logger.info(f"Running command: {' '.join(cmd)}")

    # Prepare environment variables
    environment = None
    if env:
        environment = os.environ.copy()
        environment.update(env)

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=environment,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        # Return partial output if available
        stdout = e.stdout.decode() if e.stdout else ""
        stderr = e.stderr.decode() if e.stderr else f"Command timed out after {timeout} seconds"
        return 127, stdout, stderr


def generate_random_string(length=4):
    """Generate a random string of specified length."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
