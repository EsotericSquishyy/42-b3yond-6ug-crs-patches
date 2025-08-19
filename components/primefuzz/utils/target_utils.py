"""
Copied from https://github.com/google/oss-fuzz/blob/master/infra/base-images/base-runner/test_all.py#L70
Check on all fuzz targets in $OUT."""

import asyncio
import contextlib
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
from utils.docker_utils import docker_ps, docker_stop, docker_rm, get_available_dind_hosts

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


def get_sanitizers(oss_fuzz_path, project_name):
    """Returns the list of sanitizers from project.yaml for the given project."""
    project_path = os.path.join(oss_fuzz_path, "projects", project_name)
    if not os.path.exists(project_path):
        logging.error(f"Project {project_name} not found at {project_path}")
        return []

    yaml_path = os.path.join(project_path, "project.yaml")
    if not os.path.exists(yaml_path):
        logging.error(f"project.yaml not found at {yaml_path}")
        return []

    try:
        with open(yaml_path, "r") as f:
            project_yaml = yaml.safe_load(f)
            return project_yaml.get("sanitizers", [])
    except Exception as e:
        logging.error(f"Error reading project.yaml: {e}")
        return []


def get_task_directory(task_id: str) -> Path:
    shared_crs_dir = os.getenv("CRS_MOUNT_PATH", "/tmp")
    instance_id = os.getenv("INSTANCE_ID", "default")
    task_dir = Path(shared_crs_dir) / "primetasks" / instance_id / task_id
    return task_dir


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
        if os.getenv("FUZZING_ENGINE") not in {"none", "wycheproof"}:
            with open(path, "rb") as file_handle:
                binary_contents = file_handle.read()
                if b"LLVMFuzzerTestOneInput" not in binary_contents:
                    continue
        fuzz_targets.append(filename)
    return fuzz_targets


def get_failed_check_build_targets(msg: bytes) -> List[str]:
    """Get failed check build targets from the message.

    Extracts target names from lines starting with 'BAD BUILD:'.

    Args:
        msg: Message containing build check results

    Returns:
        List of failed target names
    """
    try:
        # Pattern to match the target name from paths in BAD BUILD lines
        pattern = r"BAD BUILD:\s+.*?/([^/\s]+)\s+"

        # Find all matches
        matches = re.findall(pattern, msg.decode('utf-8'))

        # Return unique target names
        return list(set(matches))
    except Exception as e:
        logging.error(f"Error parsing check build targets: {e}")
        return []


async def kill_docker_by_name(name: str) -> bool:
    """Kill a docker container by name."""
    if not name:
        return False

    success_ret = True

    # stop the dind containers
    docker_hosts = get_available_dind_hosts(False)
    for host in docker_hosts:
        containers = docker_ps(quiet=True, name_filter=name, docker_host=host)
        logging.debug(f"Found {len(containers)} containers with name {name}")

        # Stop and remove for each matching container
        for container in containers:
            if not docker_stop(container, docker_host=host):
                success_ret = success_ret and False
            if not docker_rm(container, docker_host=host):
                success_ret = success_ret and False

    # stop the host containers
    host_containers = docker_ps(quiet=True, name_filter=name)
    for host_container in host_containers:
        if not docker_stop(host_container):
            success_ret = success_ret and False
        if not docker_rm(host_container):
            success_ret = success_ret and False

    return success_ret


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


def setup_stop_signal(task_dir: Path) -> bool:
    """Create a STOP_NOW file to signal fuzzing should stop.
    Only creates file if parent directories already exist.

    Args:
        task_id: The ID of the task to stop
    """
    try:
        # Construct path to STOP_NOW file
        stop_file = task_dir / "fuzz-tooling" / "STOP_NOW"

        # Only proceed if parent directory exists
        if stop_file.parent.exists():
            # Create (touch) the STOP_NOW file
            stop_file.touch()
            logging.info(f"Created stop signal file at {stop_file}")
            return True
        else:
            logging.warning(
                f"Task OSS fuzz directory {stop_file.parent} does not exist."
            )
            return False

    except Exception as e:
        logging.error(f"Failed to create stop signal file: {e}")


def slicing_res_file_to_arg(res_file: Path) -> str:
    """Convert a slicing result file to a list of arguments for the slicer.

    Args:
        res_file: Path to the slicing result file

    Returns:
        A clean single-line string with content like 'com.zaxxer.hikari.util.PropertyElf.**:PropertyElfFuzzer.**'
        without extra spaces or newline characters
    """
    try:
        with open(res_file, "r") as f:
            content = f.read().strip()

        # Remove any extra whitespace, newlines, or carriage returns
        content = re.sub(r"\s+", "", content)

        logging.debug(f"Parsed slicing argument: {content}")
        return content
    except Exception as e:
        logging.error(f"Failed to read slicing result file: {e}")
        return ""


def get_slicing_extra_args(slice_result, harness_name) -> str:
    """Get extra arguments from JVM slicing results.

    Args:
        slice_result: Path to the slicing result directory

    Returns:
        Extra arguments string for the fuzzer or empty string if no slicing results found
    """
    if (not slice_result) or len(slice_result) == 0:
        return "FUZZER_ARGS="

    slice_res_file = Path(slice_result) / \
        f"{harness_name}.instrumentation_includes.txt"

    if slice_res_file.exists():
        return f"FUZZER_ARGS=--instrumentation_includes={slicing_res_file_to_arg(slice_res_file)}"

    return "FUZZER_ARGS="


def replace_docker_run_in_helper_py(helper_script: Path) -> str:
    """Replace the docker_run function in the helper script with a fake version.
    """
    # Create a temporary copy of the helper script to modify
    temp_helper_script = helper_script.with_name(
        helper_script.stem + "_modified" + helper_script.suffix)
    with open(helper_script, 'r') as src, open(temp_helper_script, 'w') as dst:
        dst.write(src.read())

    # Replace docker_run with the fake version in the temporary copy
    return temp_helper_script if replace_docker_run_with_fake(temp_helper_script) else None


def replace_docker_run_with_fake(file_path: str) -> bool:
    # Read the original file
    with open(file_path, 'r') as f:
        content = f.read()

    # Define the fake function
    fake_function = '''
def docker_run(run_args, print_output=True, architecture='x86_64', propagate_exit_codes=False):
  """Fake version of docker_run that just prints the args and returns success."""
  print("FAKE DOCKER RUN CALLED WITH:")
  print("run_args:", run_args)
  return 0 if propagate_exit_codes else True

'''

    # Find the original docker_run function using regex
    pattern = r'def docker_run\([^)]*\):.*?(?=\n\S|$)'
    # Use re.DOTALL to make . match newlines
    docker_run_match = re.search(pattern, content, re.DOTALL)

    if docker_run_match:
        # Replace the function
        new_content = content.replace(
            docker_run_match.group(0), fake_function.strip() + '\n')

        # Write the modified content back to the file
        with open(file_path, 'w') as f:
            f.write(new_content)

        print(
            f"Successfully replaced docker_run with fake version in {file_path}")
        return True
    else:
        print(f"Could not find docker_run function in {file_path}")
        return False


async def list_active_tasks() -> Dict[str, Any]:
    """List all active asyncio tasks and their status."""
    tasks_info = {}

    # Get all tasks in the current event loop
    all_tasks = asyncio.all_tasks()

    for i, task in enumerate(all_tasks):
        task_info = {
            "name": getattr(task, "_name", f"Task-{i}"),
            "done": task.done(),
            "cancelled": task.cancelled(),
            "coro": str(task.get_coro()) if hasattr(task, 'get_coro') else "Unknown",
        }

        # Get exception if task is done and has exception
        if task.done() and not task.cancelled():
            try:
                exception = task.exception()
                if exception:
                    task_info["exception"] = str(exception)
            except Exception as e:
                task_info["exception_check_error"] = str(e)

        tasks_info[f"task_{i}"] = task_info


    return tasks_info


def log_action_from_metrics(*args, **kwargs):
    pass


def log_action(*args, **kwargs):
    pass
