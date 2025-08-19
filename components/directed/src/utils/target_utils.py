"""
Copied from https://github.com/google/oss-fuzz/blob/master/infra/base-images/base-runner/test_all.py#L70
Check on all fuzz targets in $OUT."""

import contextlib
import multiprocessing
import os
from pathlib import Path
import re
import subprocess
import stat
import sys
import tempfile
import logging
import psutil
import yaml
from typing import List, Dict, Any
from utils.docker_utils import docker_ps, docker_stop, docker_rm

BASE_TMP_FUZZER_DIR = "/tmp/not-out"

EXECUTABLE = stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH

IGNORED_TARGETS = [
    r"do_stuff_fuzzer",
    r"checksum_fuzzer",
    r"fuzz_dump",
    r"fuzz_keyring",
    r"xmltest",
    r"fuzz_compression_sas_rle",
    r"ares_*_fuzzer",
]

IGNORED_TARGETS_RE = re.compile("^" + r"$|^".join(IGNORED_TARGETS) + "$")


def is_elf(filepath):
    """Returns True if |filepath| is an ELF file."""
    result = subprocess.run(
        ["file", filepath], stdout=subprocess.PIPE, check=False)
    return b"ELF" in result.stdout


def is_shell_script(filepath):
    """Returns True if |filepath| is a shell script."""
    result = subprocess.run(
        ["file", filepath], stdout=subprocess.PIPE, check=False)
    return b"shell script" in result.stdout


def is_jvm_project(oss_fuzz_path, project_name):
    """Returns True if |project_name| is a JVM project."""
    project_path = os.path.join(oss_fuzz_path, "projects", project_name)
    if not os.path.exists(project_path):
        logging.error(f"Project {project_name} not found at {project_path}")
        return False

    yaml_path = os.path.join(project_path, "project.yaml")
    if not os.path.exists(yaml_path):
        logging.error(f"project.yaml not found at {yaml_path}")
        return False

    try:
        with open(yaml_path, "r") as f:
            project_yaml = yaml.safe_load(f)
            language = project_yaml.get("language", "")
            return language.lower() == "jvm"
    except Exception as e:
        logging.error(f"Error reading project.yaml: {e}")
        return False

    return False


def get_ignore_tokens(tokens_set: Dict[str, set]) -> str:
    """Join tokens from each set in the dictionary.

    Args:
        tokens_set: Dictionary of token type to set of tokens

    Returns:
        Comma-separated string of all tokens
    """
    if not tokens_set:
        return ""

    try:
        all_tokens = []
        for token_type, tokens in tokens_set.items():
            all_tokens.extend(tokens)
        return ",".join(sorted(all_tokens))
    except Exception as e:
        logging.error(f"Error joining tokens: {e}")
        return ""


def find_fuzz_targets(directory):
    """Returns paths to fuzz targets in |directory|."""
    fuzz_targets = []
    for filename in os.listdir(directory):
        path = os.path.join(directory, filename)
        if filename == "llvm-symbolizer":
            continue
        if filename.startswith("afl-"):
            continue
        if filename.startswith("jazzer_"):
            continue
        if not os.path.isfile(path):
            continue
        if not os.stat(path).st_mode & EXECUTABLE:
            continue
        # Fuzz targets can either be ELF binaries or shell scripts (e.g. wrapper
        # scripts for Python and JVM targets or rules_fuzzing builds with runfiles
        # trees).
        if not is_elf(path) and not is_shell_script(path):
            continue
        # ! As we are detecting fuzz targets outside of the fuzzer container, we do not detect the FUZZING_ENGINE
        # if os.getenv("FUZZING_ENGINE") not in {"none", "wycheproof"}:
        with open(path, "rb") as file_handle:
            binary_contents = file_handle.read()
            if b"LLVMFuzzerTestOneInput" not in binary_contents:
                continue
        fuzz_targets.append(filename)
    return fuzz_targets


def kill_docker_by_name(name):
    """Kill a docker container by name."""
    if not name:
        return False

    containers = docker_ps(quiet=True, name_filter=name)
    logging.debug(f"Found {len(containers)} containers with name {name}")
    if not containers:
        return False

    # Stop and remove for each matching container
    success = True
    for container in containers:
        if not docker_stop(container):
            success = False
        if not docker_rm(container):
            success = False

    return success


def kill_process_tree(process):
    """Kill process and all its children recursively"""
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)

        # Kill children first
        for child in children:
            child.terminate()

        # Give them some time to terminate
        gone, alive = psutil.wait_procs(children, timeout=5)

        # Force kill survivors
        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass

        # Kill parent
        process.terminate()
        process.wait(timeout=5)

    except (psutil.NoSuchProcess, psutil.TimeoutExpired) as e:
        logging.warning(f"Process already terminated or timed out: {e}")
        # Force kill parent if still alive
        try:
            process.kill()
        except (ProcessLookupError, psutil.NoSuchProcess):
            pass


def setup_stop_signal(cwd: Path, task_id: str) -> bool:
    """Create a STOP_NOW file to signal fuzzing should stop.
    Only creates file if parent directories already exist.

    Args:
        task_id: The ID of the task to stop
    """
    try:
        # Construct path to STOP_NOW file
        stop_file = cwd / task_id / "fuzz-tooling" / "STOP_NOW"

        # Only proceed if parent directory exists
        if stop_file.parent.exists():
            # Create (touch) the STOP_NOW file
            stop_file.touch()
            logging.info(f"Created stop signal file at {stop_file}")
            return True
        else:
            logging.warning(
                f"Task OSS fuzz directory {stop_file.parent} does not exist.")
            return False

    except Exception as e:
        logging.error(f"Failed to create stop signal file: {e}")