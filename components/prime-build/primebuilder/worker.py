import json
import ast
import datetime
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import redis
from loguru import logger
import random
import string

from .config import (
    OSS_FUZZ_PATH,
    OSS_FUZZ_LOCAL_PATH,
    CRS_MOUNT_PATH,
    DOCKER_PLATFORM,
    REDIS_URL,
    JOB_DATA_KEY_PREFIX,
    BASE_RUNNER_IMAGE,
    REPRODUCTION_KEY,
)
from .utils import (
    extract_archive,
    set_task_context,
    log_action,
    run_command_sync,
    run_command_sync_no_raise,
    copy_directory,
    get_project_lang,
)


def fetch_source_code(
    project_name: str,
    src_path: Path,
    task_id: str,
    share_oss_fuzz_path: Optional[Path] = None,
) -> dict:
    """
    Step 1: Fetch the oss-fuzz source code and the source code path from arguments.

    Args:
        project_name: Name of the OSS-Fuzz project
        src_path: Path to the source code
        task_id: Task identifier
        share_oss_fuzz_path: Path to a directory to copy to OSS_FUZZ_PATH
    Examples:
        fetch_source_code("zookeeper", "/crs/backup/src/round-exhibition1-zookeeper",
            "0195f1f6-117a-788f-aa72-a2365eade509",
            /crs/backup/fuzz-tooling/fuzz-tooling)
    """
    set_task_context(task_id=task_id, project=project_name)

    log_action(
        "building",
        "source_code",
        {"project": project_name, "src_path": str(
            src_path), "task_id": task_id},
    )

    # Copy shared OSS-Fuzz directory if provided
    if share_oss_fuzz_path:
        if not Path(share_oss_fuzz_path).exists():
            raise FileNotFoundError(
                f"Shared OSS-Fuzz path does not exist: {share_oss_fuzz_path}"
            )

        # local_oss_fuzz_path = OSS_FUZZ_LOCAL_PATH
        # Create a random subdirectory for OSS_FUZZ_LOCAL_PATH
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        local_oss_fuzz_path = OSS_FUZZ_LOCAL_PATH / random_suffix
        data_volume_oss_fuzz_path = OSS_FUZZ_PATH
        if not local_oss_fuzz_path.exists():
            local_oss_fuzz_path.mkdir(parents=True, exist_ok=True)

        if not data_volume_oss_fuzz_path.exists():
            data_volume_oss_fuzz_path.mkdir(parents=True, exist_ok=True)

        shared_oss_fuzz_path_task = data_volume_oss_fuzz_path / task_id
        if shared_oss_fuzz_path_task.exists():
            logger.info(
                f"Using existing OSS-Fuzz directory: {shared_oss_fuzz_path_task}")
        else:
            logger.info(
                f"Copying shared OSS-Fuzz directory from {share_oss_fuzz_path} to {local_oss_fuzz_path}"
            )
            # copy if share_oss_fuzz_path is a directory
            if share_oss_fuzz_path.is_dir():
                copy_directory(share_oss_fuzz_path,
                               local_oss_fuzz_path, task_id)
            # extract if share_oss_fuzz_path is a file
            elif share_oss_fuzz_path.is_file():
                logger.debug(
                    f"Extracting shared OSS-Fuzz archive from {share_oss_fuzz_path} to {local_oss_fuzz_path}"
                )
                extracted_path = extract_archive(
                    share_oss_fuzz_path, local_oss_fuzz_path
                )
                # move extracted_path to local_oss_fuzz_path/task_id
                logger.info(
                    f"Moving extracted OSS-Fuzz directory from {extracted_path} to {shared_oss_fuzz_path_task}"
                )
                if extracted_path.parent == local_oss_fuzz_path:
                    shutil.move(extracted_path, shared_oss_fuzz_path_task)
                    logger.info(
                        f"Moved extracted OSS-Fuzz directory to {shared_oss_fuzz_path_task}"
                    )
                else:
                    raise FileNotFoundError(
                        f"Failed to extract archive: {share_oss_fuzz_path}"
                    )
            logger.info(f"Successfully copied OSS-Fuzz directory")

    # Validate that source code exists
    if not src_path.exists():
        raise FileNotFoundError(f"Source code path does not exist: {src_path}")
    
    if src_path.is_file() and src_path.suffix in [".tar", ".gz", ".tgz"]:
        prime_volume_src_path = OSS_FUZZ_PATH.parent / "prime_builder_src" / task_id
        prime_volume_src_path.mkdir(parents=True, exist_ok=True)
        src_path = extract_archive(src_path, prime_volume_src_path)
        logger.info(
            f"Extracted source code archive to: {src_path}"
        )

    logger.info(f"Source code found at: {src_path}")

    # Store data in Redis for next step
    redis_conn = redis.from_url(REDIS_URL)
    job_data = {
        "project_name": project_name,
        "src_path": str(src_path.absolute()),
        "task_id": task_id,
    }
    redis_conn.set(f"{JOB_DATA_KEY_PREFIX}:{task_id}", str(job_data))

    return job_data


def build_image(task_id: str) -> dict:
    """
    Step 2: Build the Docker image for the project.
    """
    # Get job data from Redis
    redis_conn = redis.from_url(REDIS_URL)
    job_data_str = redis_conn.get(f"{JOB_DATA_KEY_PREFIX}:{task_id}")
    job_data = ast.literal_eval(job_data_str.decode("utf-8"))

    project_name = job_data["project_name"]

    local_oss_fuzz_path = Path(OSS_FUZZ_PATH) / task_id
    if not local_oss_fuzz_path.exists():
        raise FileNotFoundError(
            f"OSS-Fuzz path does not exist: {local_oss_fuzz_path}")

    set_task_context(task_id=task_id, project=project_name)
    helper_script = local_oss_fuzz_path / "infra/helper.py"

    log_action(
        "building",
        "service_is_up",
        {"team.id": "b3yond", "task.id": task_id, "round.id": "round-3"},
    )

    # Build image
    logger.info(f"Building image for project: {project_name}")
    run_command_sync(
        [str(helper_script), "build_image", "--pull", project_name],
        cwd=local_oss_fuzz_path,
    )

    logger.info(f"Successfully built image for project: {project_name}")

    # Save the updated job data back to Redis
    redis_conn.set(f"{JOB_DATA_KEY_PREFIX}:{task_id}", str(job_data))
    return job_data


def build_fuzzers(task_id: str) -> dict:
    """
    Step 3: Build fuzzers using Docker.
    """
    # Get job data from Redis
    redis_conn = redis.from_url(REDIS_URL)
    job_data_str = redis_conn.get(f"{JOB_DATA_KEY_PREFIX}:{task_id}")
    job_data = ast.literal_eval(job_data_str.decode("utf-8"))

    project_name = job_data["project_name"]
    src_path = Path(job_data["src_path"])
    local_oss_fuzz_path = Path(OSS_FUZZ_PATH) / task_id
    if not local_oss_fuzz_path.exists():
        raise FileNotFoundError(
            f"OSS-Fuzz path does not exist: {local_oss_fuzz_path}")

    set_task_context(task_id=task_id, project=project_name)

    # Determine language (could be more sophisticated based on project)
    language = get_project_lang(local_oss_fuzz_path, project_name) or "c++"

    # still call the python subprocess
    logger.info(f"Building fuzzers for project: {project_name}, language: {language}")

    local_oss_fuzz_path = Path(OSS_FUZZ_PATH) / task_id
    if not local_oss_fuzz_path.exists():
        raise FileNotFoundError(
            f"OSS-Fuzz path does not exist: {local_oss_fuzz_path}")

    set_task_context(task_id=task_id, project=project_name)
    helper_script = local_oss_fuzz_path / "infra/helper.py"
    run_command_sync(
        [str(helper_script), "build_fuzzers", "--clean", project_name, str(src_path)],
        cwd=local_oss_fuzz_path,
    )

    logger.info(f"Successfully built fuzzers for project: {project_name}")

    # Save the updated job data back to Redis
    redis_conn.set(f"{JOB_DATA_KEY_PREFIX}:{task_id}", str(job_data))
    return job_data


def build_image_and_fuzzers(task_id: str) -> dict:
    """
    Combined step: Build the Docker image for the project and then build fuzzers.
    
    This function combines the steps of building the Docker image and building 
    the fuzzers into one operation for convenience.
    
    Args:
        task_id: Task identifier
        
    Returns:
        dict: Updated job data
    """
    # First build the image
    job_data = build_image(task_id)
    
    # Then build the fuzzers
    job_data = build_fuzzers(task_id)
    
    logger.info(f"Successfully built image and fuzzers for task: {task_id}")
    
    return job_data

def check_build(task_id: str) -> dict:
    """
    Step 4: Check the build (optional).
    """
    # Get job data from Redis
    redis_conn = redis.from_url(REDIS_URL)
    job_data_str = redis_conn.get(f"{JOB_DATA_KEY_PREFIX}:{task_id}")
    job_data = ast.literal_eval(job_data_str.decode("utf-8"))

    local_oss_fuzz_path = Path(OSS_FUZZ_PATH) / task_id
    if not local_oss_fuzz_path.exists():
        raise FileNotFoundError(
            f"OSS-Fuzz path does not exist: {local_oss_fuzz_path}")

    project_name = job_data["project_name"]

    set_task_context(task_id=task_id, project=project_name)

    language = get_project_lang(local_oss_fuzz_path, project_name) or "c++"

    logger.info(
        f"Checking build for project: {project_name}, language: {language}")

    run_command_sync(
        [
            "docker",
            "run",
            "--privileged",
            "--shm-size=2g",
            f"--platform={DOCKER_PLATFORM}",
            "--rm",
            "-eFUZZING_ENGINE=libfuzzer",
            "-eSANITIZER=address",
            "-eARCHITECTURE=x86_64",
            f"-eFUZZING_LANGUAGE={language}",
            "-eHELPER=True",
            f"-v{local_oss_fuzz_path}/build/out/{project_name}:/out",
            "-t",
            BASE_RUNNER_IMAGE,
            "test_all.py",
        ]
    )

    logger.info(f"Build check passed for project: {project_name}")

    # Save the updated job data back to Redis
    redis_conn.set(f"{JOB_DATA_KEY_PREFIX}:{task_id}", str(job_data))
    return job_data


def copy_artifact(task_id: str) -> dict:
    """
    Step 5: Copy the artifacts to the destination directory.
    """
    # Get job data from Redis
    redis_conn = redis.from_url(REDIS_URL)
    job_data_str = redis_conn.get(f"{JOB_DATA_KEY_PREFIX}:{task_id}")
    job_data = ast.literal_eval(job_data_str.decode("utf-8"))

    project_name = job_data["project_name"]

    set_task_context(task_id=task_id, project=project_name)

    local_oss_fuzz_path = Path(OSS_FUZZ_PATH) / task_id
    if not local_oss_fuzz_path.exists():
        raise FileNotFoundError(
            f"OSS-Fuzz path does not exist: {local_oss_fuzz_path}")

    source_dir = local_oss_fuzz_path / "build" / "out" / project_name
    dest_dir = CRS_MOUNT_PATH / "public_build" / task_id / "default" / "out"

    # Create destination directory if it doesn't exist
    os.makedirs(dest_dir, exist_ok=True)

    # Copy files
    logger.info(f"Copying artifacts from {source_dir} to {dest_dir}")

    for item in source_dir.glob("*"):
        if item.is_file():
            shutil.copy2(item, dest_dir)
        elif item.is_dir():
            shutil.copytree(item, dest_dir / item.name, dirs_exist_ok=True)

    logger.info(f"Successfully copied artifacts for project: {project_name}")

    # Save the updated job data back to Redis
    redis_conn.set(f"{JOB_DATA_KEY_PREFIX}:{task_id}", str(job_data))
    return job_data


def run_fuzzer(
    task_id: str,
    harness: str,
    project: str,
    extra_args: list = ["-value_profile=1", "-max_total_time=120"],
) -> dict:
    """
    Run a fuzzer for 2 minutes.

    Args:
        task_id: Task identifier
        harness: The fuzzer harness to run
        project: Name of the project

    Returns:
        dict: Fuzzer run data
    """
    set_task_context(task_id=task_id, project=project)

    log_action(
        "dynamic_analysis",
        "fuzzer_run",
        {"project": project, "harness": harness, "task_id": task_id},
    )

    # Check if the necessary artifacts exist
    local_oss_fuzz_path = Path(OSS_FUZZ_PATH) / task_id
    artifact_path = local_oss_fuzz_path / "build" / "out" / project

    if not artifact_path.exists():
        raise FileNotFoundError(
            f"Fuzzer artifacts not found at: {artifact_path}")

    logger.info(f"Running fuzzer {harness} for project: {project}")

    # Run the fuzzer
    return_code, stdout, stderr = run_command_sync_no_raise(
        [
            "docker",
            "run",
            "--privileged",
            "--shm-size=2g",
            f"--platform={DOCKER_PLATFORM}",
            "--rm",
            "-d",
            "-e",
            "FUZZING_ENGINE=libfuzzer",
            "-e",
            "SANITIZER=address",
            "-e",
            "HELPER=True",
            "-v",
            f"{artifact_path}:/out",
            "-t",
            BASE_RUNNER_IMAGE,
            "run_fuzzer",
            harness,
            " ".join(extra_args),
        ]
    )

    output = stdout + stderr
    logger.info(
        f"Fuzzer {harness} completed for project: {project} with return code {return_code}"
    )

    # Store run data in Redis
    redis_conn = redis.from_url(REDIS_URL)
    run_data = {
        "project": project,
        "harness": harness,
        "task_id": task_id,
        "timestamp": str(datetime.datetime.now()),
        "status": "completed" if return_code == 0 else "crashed",
        "return_code": return_code,
        "output": output[-256:] if len(output) > 256 else output,
    }

    redis_key = f"prime:fuzzer_run:{task_id}:{harness}"
    redis_conn.set(redis_key, json.dumps(run_data))

    return run_data


def reproduce(
    task_id: str, artifact_path_str: str, project: str, harness: str, testcase: str
) -> dict:
    """
    Reproduce a fuzzer crash using the specified harness and testcase.

    Args:
        task_id: Task identifier
        artifact_path: Path to the fuzzer artifacts
        project: Name of the project
        harness: The fuzzer harness to use for reproduction
        testcase: Path to the test case file

    Returns:
        dict: Reproduction result data
    """
    set_task_context(task_id=task_id, project=project)

    log_action(
        "dynamic_analysis",
        "fuzzer_crash",
        {"project": project, "harness": harness, "testcase": testcase},
    )

    logger.info(
        f"Reproducing crash for project: {project} with harness: {harness}")

    # Convert paths to Path objects to ensure they exist
    artifact_path = Path(artifact_path_str)
    testcase_path = Path(testcase)

    if not artifact_path.exists():
        raise FileNotFoundError(
            f"Artifact path does not exist: {artifact_path}")

    if not testcase_path.exists():
        raise FileNotFoundError(
            f"Testcase path does not exist: {testcase_path}")

    # Run reproduction command with no_raise version to analyze return code
    return_code, stdout, stderr = run_command_sync_no_raise(
        [
            "docker",
            "run",
            "--privileged",
            "--shm-size=2g",
            f"--platform={DOCKER_PLATFORM}",
            "--rm",
            "-e",
            "HELPER=True",
            "-e",
            "ARCHITECTURE=x86_64",
            "-v",
            f"{artifact_path}:/out",
            "-v",
            f"{testcase_path}:/testcase",
            "-t",
            BASE_RUNNER_IMAGE,
            "reproduce",
            harness,
            "-runs=100",
        ]
    )

    # Combine stdout and stderr for analysis
    output = stdout + stderr

    # Analyze the return code and output
    status = "UNKNOWN"
    result_details = {}
    redis_key_prefix = REPRODUCTION_KEY

    if return_code == 0:
        logger.warning(
            f"Crash reproduction returns {return_code}: the fuzzer did not crash: {output[-256:]}"
        )
        status = "NO_CRASH"
        result_details["desc"] = "Fuzzer did not crash"
    elif return_code == 70 or "ERROR: libFuzzer: timeout after" in output:
        # This means timeout
        logger.info(
            f"Crash reproduction with libFuzzer timeout: {output[-128:]}")
        status = "TIMEOUT"
        result_details["timeout"] = True
    else:
        # Actual crash occurred
        logger.info(
            f"Crash reproduction successful with return code {return_code}")
        status = "CRASH"
        result_details["crash_return_code"] = return_code

    logger.info(f"Reproduction completed for project: {project}")

    # Store reproduction result in Redis with a new key
    redis_conn = redis.from_url(REDIS_URL)
    reproduction_data = {
        "project": project,
        "harness": harness,
        "testcase": str(testcase_path),
        "status": status,
        "return_code": return_code,
        "output": output[-128:],
        "result_details": result_details,
        "timestamp": str(datetime.datetime.now()),
    }

    # Create a unique key for this reproduction
    repro_key = f"{redis_key_prefix}:{task_id}:{harness}:{testcase_path.name}"
    redis_conn.set(repro_key, json.dumps(reproduction_data))

    logger.info(f"Saved reproduction result with key: {repro_key}")

    return reproduction_data


def run_worker(
    project_name: str,
    source_path: str,
    task_id: str,
    share_oss_fuzz_path: Optional[str] = None,
    timeout: int = 600,  # Set default timeout to 600 seconds
) -> dict:
    """
    Run the complete worker pipeline from source fetching to artifact copying.

    Args:
        project_name: Name of the OSS-Fuzz project
        source_path: Path to the source code
        task_id: Task identifier
        share_oss_fuzz_path: Path to a shared OSS-Fuzz directory
        timeout: Maximum execution time in seconds (default: 600)

    Returns:
        dict: Job data after pipeline completion
    """
    logger.info(f"Starting worker pipeline for project: {project_name} with timeout: {timeout} seconds")
    src_path = Path(source_path)
    share_path = Path(share_oss_fuzz_path) if share_oss_fuzz_path else None

    # Execute pipeline steps
    job_data = fetch_source_code(project_name, src_path, task_id, share_path)
    job_data = build_image(task_id)
    job_data = build_fuzzers(task_id)
    job_data = check_build(task_id)
    # job_data = copy_artifact(task_id)

    logger.info(
        f"Worker pipeline completed successfully for project: {project_name}")
    return job_data
