import shlex
import sys
import subprocess
import logging
import os
from typing import List
import uuid

def _get_command_string(command):
    """Returns a shell escaped command string."""
    return " ".join(shlex.quote(part) for part in command)


def _env_to_docker_args(env_list):
    """Turns envirnoment variable list into docker arguments."""
    return sum([["-e", v] for v in env_list], [])


def docker_run(run_args, print_output=True, architecture="x86_64"):
    """Calls `docker run`."""
    platform = "linux/arm64" if architecture == "aarch64" else "linux/amd64"
    command = ["docker", "run", "--privileged", "--shm-size=2g", "--platform", platform]
    if os.getenv("OSS_FUZZ_SAVE_CONTAINERS_NAME"):
        command.append("--name")
        command.append(os.getenv("OSS_FUZZ_SAVE_CONTAINERS_NAME"))
    else:
        command.append("--rm")

    # Support environments with a TTY.
    if sys.stdin.isatty():
        command.append("-i")

    command.extend(run_args)

    logging.info("Running: %s.", _get_command_string(command))
    stdout = None
    if not print_output:
        stdout = open(os.devnull, "w")

    try:
        subprocess.check_call(command, stdout=stdout, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        return False

    return True


def docker_ps(all=True, quiet=False, name_filter=None) -> List[str]:
    """Calls `docker ps` and returns container IDs.
    Args:
        all: Show all containers (default shows just running)
        quiet: Only display container IDs
        name_filter: Filter by container name
    """
    command = ["docker", "ps"]
    if all:
        command.append("-a")
    if quiet:
        command.append("-q")
    if name_filter:
        command.extend(["--filter", f"name={name_filter}"])

    logging.info("Running: %s.", _get_command_string(command))

    try:
        output = subprocess.check_output(command, stderr=subprocess.STDOUT)
        containers = output.decode().strip().split("\n")
        return [c for c in containers if c]
    except subprocess.CalledProcessError:
        logging.error("Failed to list containers")
        return []


def docker_stop(container_name):
    """Calls `docker stop`."""
    command = ["docker", "stop", container_name]
    logging.info("Running: %s.", _get_command_string(command))

    try:
        subprocess.check_call(command, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        logging.error("Failed to stop container: %s", container_name)
        return False


def docker_rm(container_name):
    """Calls `docker rm`."""
    command = ["docker", "rm", container_name]
    logging.debug("Running: %s.", _get_command_string(command))

    try:
        subprocess.check_call(command, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        logging.error("Failed to remove container: %s", container_name)
        return False


def docker_prune() -> bool:
    """Calls `docker container prune -f` to remove all stopped containers.

    Returns:
        bool: True if successful, False otherwise
    """
    command = ["docker", "container", "prune", "-f"]
    logging.debug("Running: %s.", _get_command_string(command))

    try:
        subprocess.check_call(command, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        logging.error("Failed to prune containers")
        return False

def docker_run_background(run_args, architecture='x86_64'):
    """
    Calls `docker run` as a detached background process.
    
    Returns:
        str: The container ID of the started container.
    
    Raises:
        RuntimeError: If the docker run command fails.
    """
    platform = 'linux/arm64' if architecture == 'aarch64' else 'linux/amd64'
    # Run in detached mode using '-d'
    command = [
        'docker', 'run', '-d', '--privileged', '--shm-size=2g', '--platform', platform
    ]
    if os.getenv('OSS_FUZZ_SAVE_CONTAINERS_NAME'):
        command.extend(['--name', os.getenv('OSS_FUZZ_SAVE_CONTAINERS_NAME')])
    else:
        command.extend(['--name', f'crs-directed-{uuid.uuid4()}'])
        command.append('--rm')

    # Detached mode doesn't require TTY flags.
    command.extend(run_args)
    logging.info('Running (detached): %s.', _get_command_string(command))
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        logging.error("Failed to run docker container: %s", result.stderr)
        raise RuntimeError("Docker run failed")
    container_id = result.stdout.strip()
    return container_id