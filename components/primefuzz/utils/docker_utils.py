import socket
import logging
import os
import shlex
import subprocess
import docker
import sys
import threading
import concurrent.futures
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from modules.redis_middleware import RedisMiddleware

BASE_RUNNER_IMAGE = "gcr.io/oss-fuzz-base/base-runner"
logger = logging.getLogger(__name__)


@dataclass
class ProjectPaths:
    out: Path  # Build output directory


@dataclass
class RunnerConfig:
    project: ProjectPaths
    fuzzer_name: str
    engine: str = "libfuzzer"
    sanitizer: str = "address"
    corpus_dir: Optional[Path] = None
    architecture: str = "x86_64"
    fuzzer_args: List[str] = field(default_factory=list)
    e: List[str] = field(default_factory=list)  # Additional env vars


def _get_command_string(command):
    """Returns a shell escaped command string."""
    return " ".join(shlex.quote(part) for part in command)


def _env_to_docker_args(env_list):
    """Turns envirnoment variable list into docker arguments."""
    return sum([["-e", v] for v in env_list], [])


def docker_run(run_args, print_output=True, architecture="x86_64"):
    """Calls `docker run`."""
    platform = "linux/arm64" if architecture == "aarch64" else "linux/amd64"
    command = ["docker", "run", "--privileged",
               "--shm-size=2g", "--platform", platform]
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
        stdout = open(os.devnull, "wb")

    try:
        subprocess.check_call(command, stdout=stdout, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        return False

    return True


def docker_ps(all=True, quiet=False, name_filter=None, docker_host: str = None) -> List[str]:
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
        command.extend(["--filter", f"name={name_filter}$"])

    logger.info("Running: %s.", _get_command_string(command))

    try:
        if docker_host:
            env = os.environ.copy()
            env["DOCKER_HOST"] = f"tcp://{docker_host}:2375"
            output = subprocess.check_output(
                command, stderr=subprocess.STDOUT, env=env)
        else:
            output = subprocess.check_output(command, stderr=subprocess.STDOUT)
        containers = output.decode(errors='ignore').strip().split("\n")
        return [c for c in containers if c]
    except subprocess.CalledProcessError:
        logger.error("Failed to list containers")
        return []


def docker_stop(container_name, docker_host: str = None):
    """Calls `docker stop`."""
    command = ["docker", "stop", container_name]
    logger.info("Running: %s.", _get_command_string(command))

    try:
        # for all dind pods
        if docker_host:
            env = os.environ.copy()
            env["DOCKER_HOST"] = f"tcp://{docker_host}:2375"
            subprocess.check_call(command, stderr=subprocess.STDOUT, env=env)
        else:
            subprocess.check_call(command, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        logger.error("Failed to stop container: %s", container_name)
        return False


def docker_rm(container_name, docker_host: str = None):
    """Calls `docker rm`."""
    command = ["docker", "rm", container_name]
    logger.debug("Running: %s.", _get_command_string(command))

    try:
        # for all dind pods
        if docker_host:
            env = os.environ.copy()
            env["DOCKER_HOST"] = f"tcp://{docker_host}:2375"
            subprocess.check_call(command, stderr=subprocess.STDOUT, env=env)
        else:
            subprocess.check_call(command, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        logger.error("Failed to remove container: %s", container_name)
        return False


def docker_prune(docker_host: str = None) -> bool:
    """Calls `docker container prune -f` to remove all stopped containers.

    Returns:
        bool: True if successful, False otherwise
    """
    command = ["docker", "container", "prune", "-f"]
    logger.debug("Running: %s.", _get_command_string(command))

    try:
        if docker_host:
            env = os.environ.copy()
            env["DOCKER_HOST"] = f"tcp://{docker_host}:2375"
            subprocess.check_call(command, stderr=subprocess.STDOUT, env=env)
        else:
            subprocess.check_call(command, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        logger.error("Failed to prune containers")
        return False


def get_node_cpu_usage(docker_client, timeout_seconds=60, default_value=3200.0):
    """
    Calculate total CPU usage (%) of all containers on a given Docker node.
    Returns default_value (3200.0) if operation takes longer than timeout_seconds (60s).
    """
    result = [default_value]  # Use mutable container to store result

    def calculate_cpu():
        total_cpu = 0.0
        containers = docker_client.containers.list()  # list running containers
        for container in containers:
            try:
                # Fetch one-time stats (non-streaming) for the container
                stats = container.stats(stream=False)
                # Calculate CPU percentage using Docker stats formula
                cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                    stats["precpu_stats"]["cpu_usage"]["total_usage"]
                system_delta = stats["cpu_stats"]["system_cpu_usage"] - \
                    stats["precpu_stats"]["system_cpu_usage"]
                # Number of CPUs available (online_cpus) or fall back to CPU count
                online_cpus = stats["cpu_stats"].get("online_cpus") or len(
                    stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [])) or 1
                if system_delta > 0 and cpu_delta > 0:
                    cpu_percent = (cpu_delta / system_delta) * \
                        online_cpus * 100.0
                else:
                    cpu_percent = 0.0
                total_cpu += cpu_percent
            except docker.errors.NotFound as e:
                # Container exited before stats could be retrieved
                logger.debug(
                    f"Skipping container {container.id}: Container exited before stats retrieval - {e}")
                continue
            except docker.errors.APIError as e:
                logger.warning(
                    f"API error when getting stats for container {container.id}: {e}")
                continue
            except Exception as e:
                logger.warning(
                    f"Failed to get stats for container {container.id}: {e}")
                continue
        result[0] = total_cpu

    # Run calculation in a separate thread with timeout
    thread = threading.Thread(target=calculate_cpu)
    thread.daemon = True
    thread.start()
    thread.join(timeout_seconds)

    if result[0] == default_value:
        logger.warning(
            f"CPU usage calculation timed out after {timeout_seconds}s, returning default value")

    return result[0]


def check_docker_host(host: str) -> bool:
    """Check if the Docker host is reachable."""
    try:
        client = docker.DockerClient(
            base_url=f"tcp://{host}:2375", timeout=60, tls=False)
        client.ping()
        return True
    except docker.errors.DockerException as e:
        logger.error(f"Failed to connect to Docker host {host}: {e}")
        return False


def get_available_dind_hosts(check_host=True) -> List[str]:
    redis_client = RedisMiddleware()
    docker_hosts = redis_client.get_docker_hosts()
    if not docker_hosts:
        logger.warning(
            "No available docker hosts found remotely. Using localhost.")
        return []

    docker_hosts_in_ipv4 = set()

    # Process each host - check if IP or domain name
    for host in docker_hosts:
        try:
            # Check if the host is already an IPv4 address
            socket.inet_pton(socket.AF_INET, host)
            # If no exception, it's a valid IPv4 address
            docker_hosts_in_ipv4.add(host)
            logger.debug(f"Added IPv4 address: {host}")
        except socket.error:
            # Not an IPv4 address, try to resolve the hostname
            try:
                # Get all IPv4 addresses for the hostname
                ip_addresses = socket.getaddrinfo(host, None, socket.AF_INET)
                resolved = False
                for ip_info in ip_addresses:
                    ip = ip_info[4][0]  # Extract the IP address
                    if ip not in docker_hosts_in_ipv4:
                        docker_hosts_in_ipv4.add(ip)
                        resolved = True
                        logger.debug(f"Resolved {host} to IPv4 address: {ip}")

                # If resolution returned no results, use original hostname
                if not resolved:
                    docker_hosts_in_ipv4.add(host)
                    logger.info(
                        f"No IPv4 addresses found for {host}, using original hostname")
            except socket.gaierror as e:
                logger.warning(f"Could not resolve hostname {host}: {e}")
                logger.info(f"Skip adding unresolved hostname {host} to be checked")
                # do not add original hostname in case Docker can resolve it
                # docker_hosts_in_ipv4.add(host)

    # Filter for online docker hosts
    if check_host:
        online_hosts = [
            host for host in docker_hosts_in_ipv4 if check_docker_host(host)]
    else:
        online_hosts = list(docker_hosts_in_ipv4)

    return online_hosts


def get_lowest_cpu_docker_host(docker_hosts: list) -> str:
    """
    Get the docker host with the lowest CPU usage.
    Returns:
        str: The docker host with the lowest CPU usage.
    """
    lowest_cpu_host = ""
    try:
        max_load = float(os.getenv("MAX_LOAD", "2440.0"))
        lowest_cpu_usage = max_load
    except ValueError:
        logger.warning(f"Invalid MAX_LOAD value, defaulting to 2440.0")
        max_load = 2440.0
        lowest_cpu_usage = max_load

    # Create a function to check CPU usage for a single host

    def check_host_cpu(host):
        try:
            client = docker.DockerClient(
                base_url=f"tcp://{host}:2375", timeout=60, tls=False)
            cpu_usage = get_node_cpu_usage(client)
            logger.info(f"CPU usage [P], {host}: {cpu_usage:.2f}%")
            return (host, cpu_usage)
        except Exception as e:
            logger.error(f"Failed to get CPU usage for {host}: {e}")
            return (host, float('inf'))  # Return infinity for failed hosts

    # Use ThreadPoolExecutor to run checks in parallel
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit tasks and get futures
        futures = [executor.submit(check_host_cpu, host)
                   for host in docker_hosts]

        # Process results as they complete
        for future in concurrent.futures.as_completed(futures):
            host, cpu_usage = future.result()
            if cpu_usage < lowest_cpu_usage:
                lowest_cpu_host = host
                lowest_cpu_usage = cpu_usage

    return lowest_cpu_host


def get_docker_image_id(project_name: str, docker_host: str = None) -> str:
    """
    Get the Docker image ID for a given project name.
    like docker image ls | grep "aixcc-afc/$PROJECT_NAME" | awk '{print $3}'

    Args:
        project_name: The name of the project
        docker_host: Optional Docker host to connect to

    Returns:
        The Docker image ID if found, otherwise an empty string
    """
    command = ["docker", "image", "ls", "--format",
               "{{.ID}}", f"aixcc-afc/{project_name}"]
    logger.debug("Running: %s.", _get_command_string(command))

    try:
        if docker_host:
            env = os.environ.copy()
            env["DOCKER_HOST"] = f"tcp://{docker_host}:2375"
            output = subprocess.check_output(
                command, stderr=subprocess.STDOUT, env=env)
        else:
            output = subprocess.check_output(command, stderr=subprocess.STDOUT)

        image_id = output.decode(errors='ignore').strip()
        if image_id:
            logger.info(
                f"Found image ID {image_id} for project {project_name}")
            return image_id
        else:
            logger.info(f"No Docker image found for project {project_name}")
            return ""
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Failed to get Docker image ID for project {project_name}: {e}")
        return ""


def run_fuzzer(runner_config: RunnerConfig):
    """
    Runs a fuzzer in the container.
    e.g
    docker run --privileged --shm-size=2g --platform linux/amd64 --rm -i \
        -e FUZZING_ENGINE=libfuzzer \
        -e SANITIZER=address \
        -e RUN_FUZZER_MODE=interactive \
        -e HELPER=True \
        -v PATH/fuzz-tooling/build/work/libpng/corpus/libpng_read_fuzzer:/tmp/libpng_read_fuzzer_corpus \
        -v /home/yun/code/aixcc/crs-prime-fuzz/3d4d50f9-a8fd-4144-afb5-dde1ed642126/fuzz-tooling/build/out/libpng:/out \
        -t gcr.io/oss-fuzz-base/base-runner run_fuzzer libpng_read_fuzzer \
            -rss_limit_mb=4096 -detect_leaks=0 -timeout=2 -fork=2 \
            -ignore_ooms=1 -ignore_timeouts=1 -ignore_crashes=1 \
            -create_missing_dirs=1 -artifact_prefix=/out/artifacts/libpng_read_fuzzer/
    """

    env = [
        "FUZZING_ENGINE=" + runner_config.engine,
        "SANITIZER=" + runner_config.sanitizer,
        "RUN_FUZZER_MODE=interactive",
        "HELPER=True",
    ]

    # a list of additional environment variables
    if runner_config.e:
        env += runner_config.e

    run_args = _env_to_docker_args(env)

    if runner_config.corpus_dir:
        if not os.path.exists(runner_config.corpus_dir):
            logger.error(
                "The path provided in --corpus-dir argument does not exist")
            return False
        corpus_dir = os.path.realpath(runner_config.corpus_dir)
        run_args.extend(
            [
                "-v",
                "{corpus_dir}:/tmp/{fuzzer}_corpus".format(
                    corpus_dir=corpus_dir, fuzzer=runner_config.fuzzer_name
                ),
            ]
        )

    run_args.extend(
        [
            "-v",
            "%s:/out" % runner_config.project.out,
            "-t",
            BASE_RUNNER_IMAGE,
            "run_fuzzer",
            runner_config.fuzzer_name,
        ]
        + runner_config.fuzzer_args
    )

    return docker_run(run_args, architecture=runner_config.architecture)
