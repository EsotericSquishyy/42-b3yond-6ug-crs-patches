import os
import traceback
import pika.exceptions
import tarfile
import subprocess
import shutil
import json
import threading
import functools
import hashlib
import uuid
import random
from dataclasses import dataclass
from typing import List

import pika
import redis

from infra.oss_fuzz import find_fuzzers, compile_project, replay_poc, run_container, cleanup_containers
from parser.unifiedparser import UnifiedSanitizerReport
from parser.jazzer import JazzerSanitizerReport
from dedup.workflow import do_dedup

from utils.task import TaskData
from utils.telemetry import init_opentelemetry, log_triage
from utils.redis import init_redis, get_redis_client
import utils.db as db

INSTANCE_ID = uuid.uuid4()

TASK_BUG_CLUSTERS_KEY = "global:task_bug_clusters"


def extract_from_storage(tar_path: str, dest_dir: str) -> str:
    """
    Extract a local .tar.gz file (tar_path) into dest_dir, 
    then return the top-level directory if there's exactly one.
    """
    if not tar_path:
        return ""

    with tarfile.open(tar_path, 'r:gz') as tar:
        top_level_dirs = set()
        for member in tar.getmembers():
            root = os.path.normpath(member.name).split('/')[0]
            if root:  # Make sure it's not empty
                top_level_dirs.add(root)

        # Remove existing residual extracted files (in case of a task being requeued)
        for root in top_level_dirs:
            existing_path = os.path.join(dest_dir, root)
            if os.path.exists(existing_path):
                if os.path.isdir(existing_path):
                    shutil.rmtree(existing_path)
                else:
                    os.remove(existing_path)

        # Extract all files
        tar.extractall(path=dest_dir)

    # If there's exactly one top-level directory, return it
    if len(top_level_dirs) == 1:
        return top_level_dirs.pop()

    return None


def build_project(task: TaskData, sanitizer: str, storage_dir: str, apply_diff: bool):
    """
    Given a TaskData, extract the repos, fuzzing_tooling, diff archives
    into a .tmp/bugs/<bug_id> folder and run the PoC.
    """

    # Define directories for caching builds and the working build environment.
    if apply_diff:
        repo_state = "patched"
    else:
        repo_state = "unpatched"

    cache_dir = os.path.abspath(os.path.join(".tmp", "build_cache", task.task_id,
                                             sanitizer, repo_state))

    # Define a file within the working directory to store the name of the extracted fuzz_tooling folder.
    fuzz_tooling_file = os.path.join(cache_dir, "fuzz_tooling_dir.txt")

    redis_build_lock = f"lock:triage:global:{task.task_id}:{sanitizer}:{repo_state}:build"
    lock = redis.lock.Lock(get_redis_client(), redis_build_lock, timeout=600)

    if lock.acquire(blocking=True):
        try:
            build_status_key = f"triage:global:{task.task_id}:{sanitizer}:{repo_state}:build_status"
            build_status = get_redis_client().get(build_status_key)
            if build_status is not None and build_status.decode("utf-8") == "done":
                print(
                    f"[*] Cache found for task_id {task.task_id}. Using cached repos and fuzz tooling.")
                # Use the global build cache in the storage
                cache_dir = os.path.abspath(os.path.join(storage_dir, "triage", "build_cache",
                                                         task.task_id, sanitizer, repo_state))
                fuzz_tooling_file = os.path.join(
                    cache_dir, "fuzz_tooling_dir.txt")

            else:
                get_redis_client().set(build_status_key, "building")
                os.makedirs(cache_dir, exist_ok=True)

                # Extract repos
                extracted_repos = []
                for repo_path in task.repo:
                    folder_name = extract_from_storage(repo_path, cache_dir)
                    extracted_repos.append(folder_name)

                # Extract fuzz_tooling
                fuzz_tooling_dir = extract_from_storage(
                    task.fuzz_tooling, cache_dir)
                if fuzz_tooling_dir is not None:
                    # Save the extracted fuzz_tooling folder name for later (so we can recover it from the cache).
                    with open(fuzz_tooling_file, "w") as f:
                        f.write(fuzz_tooling_dir)
                else:
                    print("[!] Fuzz tooling extraction failed or returned None.")

                # Extract diff
                diff_dir = extract_from_storage(task.diff, cache_dir)

                print("[*] All archives have been extracted.")
                print(f"- Task directory: {cache_dir}")
                print(f"- Repo directories extracted: {extracted_repos}")
                print(f"- Fuzz tooling extracted into: {fuzz_tooling_dir}")
                print(f"- Diff extracted into: {diff_dir}")

                # Apply the diff files
                if diff_dir and apply_diff:
                    diff_path = os.path.join(cache_dir, diff_dir)
                    apply_diff_command = [
                        "patch", "--batch", "--no-backup-if-mismatch", "-p1"]

                    if os.path.isfile(diff_path) and (diff_path.endswith('.patch') or diff_path.endswith('.diff')):
                        # diff_dir is a file, so apply it directly
                        with open(diff_path, "rb") as patch_file:
                            subprocess.run(apply_diff_command, stdin=patch_file, check=True, cwd=os.path.join(
                                cache_dir, task.focus))
                        print(
                            f"[+] Applied diff from {diff_path} to {task.focus}")

                    elif os.path.isdir(diff_path):
                        # diff_dir is a directory, so iterate over contained patch/diff files
                        diff_files = [f for f in os.listdir(diff_path) if f.endswith(
                            '.patch') or f.endswith('.diff')]
                        for diff_file in diff_files:
                            diff_file_path = os.path.join(diff_path, diff_file)
                            if os.path.exists(diff_file_path):
                                with open(diff_file_path, "rb") as patch_file:
                                    subprocess.run(apply_diff_command, stdin=patch_file, check=True, cwd=os.path.join(
                                        cache_dir, task.focus))
                                print(
                                    f"[+] Applied diff from {diff_file_path} to {task.focus}")
                            else:
                                print(
                                    f"[!] Diff file {diff_file_path} does not exist")
                    else:
                        print(
                            f"[!] The provided diff path {diff_path} is neither a valid file nor a directory.")

                compile_project(
                    fuzz_tooling=os.path.join(cache_dir, fuzz_tooling_dir),
                    project_name=task.project_name,
                    sanitizer=sanitizer,
                    src_path=os.path.join(cache_dir, task.focus)
                )

                # Copy fuzz_tooling/build/out to global cache
                global_cache_dir = os.path.abspath(os.path.join(storage_dir, "triage", "build_cache",
                                                   task.task_id, sanitizer, repo_state))
                rel_out_path = os.path.join(
                    fuzz_tooling_dir, "build", "out", task.project_name)
                src_out_dir = os.path.join(cache_dir, rel_out_path)
                dst_out_dir = os.path.join(global_cache_dir, rel_out_path)
                dst_fuzz_tooling_file = os.path.join(
                    global_cache_dir, "fuzz_tooling_dir.txt")
                os.makedirs(os.path.dirname(dst_out_dir), exist_ok=True)
                if os.path.exists(src_out_dir):
                    shutil.copytree(src_out_dir, dst_out_dir,
                                    dirs_exist_ok=True)
                    shutil.copy2(fuzz_tooling_file, dst_fuzz_tooling_file)
                else:
                    raise FileNotFoundError(
                        f"Build output not found in cache_dir: {src_out_dir}")
                # Operate only on the global cache from this point
                cache_dir = global_cache_dir

                get_redis_client().set(build_status_key, "done")

            # Retrieve the name of the fuzz_tooling folder (it was saved during extraction).
            if os.path.exists(fuzz_tooling_file):
                with open(fuzz_tooling_file, "r") as f:
                    cached_fuzz_tooling_dir = f.read().strip()
            else:
                raise Exception("Fuzz tooling directory not found.")

            runner_status_key = f"triage:{INSTANCE_ID}:{task.task_id}:{sanitizer}:{repo_state}:runner_status"
            runner_status = get_redis_client().get(runner_status_key)
            if runner_status is not None and runner_status.decode("utf-8") == "launched":
                print(
                    f"[*] Runner container exists for {task.task_id}:{sanitizer}:{repo_state}")
            else:
                get_redis_client().set(runner_status_key, "launching")
                poc_dir = os.path.abspath(os.path.join(".tmp", "poc"))
                os.makedirs(poc_dir, exist_ok=True)
                run_container(
                    fuzz_tooling=os.path.join(
                        cache_dir, cached_fuzz_tooling_dir),
                    project_name=task.project_name,
                    poc_dir=poc_dir
                )
                get_redis_client().set(runner_status_key, "launched")

        finally:
            try:
                lock.release()
            except redis.exceptions.LockNotOwnedError:
                # Lock expired, ignore the exception
                pass

    # Return the path needed for the PoC replay process.
    return os.path.join(cache_dir, cached_fuzz_tooling_dir)


def send_to_patch_queue(
    connection: pika.BlockingConnection,
    bug_profile_id: int,
    patch_mode: str,
    priority: int
):
    """
    Send a message to the patch_queue with the given bug_profile_id, patch_mode, and priority.
    Creates a new connection for thread safety.
    """
    try:
        channel = connection.channel()

        # Declare the queue with priority support
        channel.queue_declare(
            queue="patch_queue",
            durable=True,
            arguments={"x-max-priority": 10}
        )

        # Create the message
        message = json.dumps({
            "bug_profile_id": bug_profile_id,
            "patch_mode": patch_mode
        })

        # Publish the message with the specified priority
        channel.basic_publish(
            exchange="",
            routing_key="patch_queue",
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
                priority=priority
            )
        )

        print(
            f"[*] Sent bug_profile_id {bug_profile_id} to patch_queue with mode {patch_mode} and priority {priority}")

    except Exception as e:
        print(f"[!] Failed to send to patch_queue: {e}")


def send_to_dedup_queue(
    connection: pika.BlockingConnection,
    task: TaskData,
    bug_profile_id: int
):
    try:
        channel = connection.channel()

        # Declare the queue with priority support
        channel.queue_declare(
            queue="dedup_queue",
            durable=True
        )

        # Create the message
        message = json.dumps({
            "task_id": task.task_id,
            "task_type": task.task_type,
            "project_name": task.project_name,
            "focus": task.focus,
            "repo": task.repo,
            "fuzz_tooling": task.fuzz_tooling,
            "diff": task.diff,
            "bug_profile_id": bug_profile_id
        })

        # Publish the message with the specified priority
        channel.basic_publish(
            exchange="",
            routing_key="dedup_queue",
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2
            )
        )

        print(f"[*] Sent bug_profile_id {bug_profile_id} to dedup_queue")

    except Exception as e:
        print(f"[!] Failed to send to dedup_queue: {e}")


def send_to_timeout_queue(
    connection: pika.BlockingConnection,
    task: TaskData
):
    try:
        channel = connection.channel()

        # Declare the queue with priority support
        channel.queue_declare(
            queue="timeout_queue",
            durable=True,
            arguments={"x-max-priority": 10}
        )

        # Create the message
        message = json.dumps({
            "bug_id": task.bug_id,
            "task_id": task.task_id,
            "task_type": task.task_type,
            "sanitizer": task.sanitizer,
            "harness_name": task.harness_binary,
            "poc_path": task.poc_path,
            "project_name": task.project_name,
            "focus": task.focus,
            "repo": task.repo,
            "fuzzing_tooling": task.fuzz_tooling,
            "diff": task.diff
        })

        # Publish the message with the specified priority
        channel.basic_publish(
            exchange="",
            routing_key="timeout_queue",
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,
                priority=10
            )
        )

        print(f"[*] Sent bug_id {task.bug_id} to timeout_queue")

    except Exception as e:
        print(f"[!] Failed to send to timeout_queue: {e}")


def get_task_bug_clusters(task_id: str) -> List[int]:
    """
    Get the list of bug profile IDs associated with a task.
    """
    bug_clusters_json = get_redis_client().hget(TASK_BUG_CLUSTERS_KEY, task_id)
    if bug_clusters_json:
        return json.loads(bug_clusters_json)
    return []


def send_active_task_bug_clusters(connection: pika.BlockingConnection, database_url: str):
    """
    Send all smallest bug profiles in all bug clusters for active tasks
    to the patch queue with patch_mode "fast" and a random priority between 3 and 7.
    """
    # Get all task IDs from the hash map
    all_task_ids = get_redis_client().hkeys(TASK_BUG_CLUSTERS_KEY)

    for task_id_bytes in all_task_ids:
        task_id = task_id_bytes.decode('utf-8')

        # Check if the task is still active
        task_status_key = f"global:task_status:{task_id}"
        task_status = get_redis_client().get(task_status_key)

        if task_status is not None and task_status.decode('utf-8') in ["processing", "waiting"]:
            # Task is active, get its bug clusters
            bug_clusters = get_task_bug_clusters(task_id)

            # For each bug cluster, get the smallest profile ID and send it
            for bug_cluster_id in bug_clusters:
                # Get the smallest profile ID in this cluster
                smallest_profile_id = db.query_for_smallest_profile_id(
                    bug_cluster_id, database_url)
                if smallest_profile_id:
                    # Send with patch_mode "fast" and random priority 3-7
                    priority = random.randint(3, 7)
                    send_to_patch_queue(
                        connection, smallest_profile_id, "fast", priority)


def dedup_and_update_db(
    task: TaskData,
    sanitizer: str,
    harness: str,
    database_url: str,
    bug_type: str,
    trigger_point: str,
    summary: str,
    diff_only: bool,
    rabbitmq_host: str,
    storage_dir: str,
    model: str
):
    # TIMEOUT_OOM_TRIAGE = "sender" means this instance will send the bug to timeout/OOM triage
    # TIMEOUT_OOM_TRIAGE = "processor" means this instance will process timeout/OOM only
    # TIMEOUT_OOM_TRIAGE = "none" means we don't use a separate pod for timeout/OOM triage
    # If this is a timeout/OOM, send it to timeout triage if this is not a timeout/OOM triage instance
    # Otherwise, process it
    if bug_type in ["timeout", "out-of-memory"] and os.getenv("TIMEOUT_OOM_TRIAGE", "none") == "sender":
        timeout_connection = pika.BlockingConnection(
            pika.URLParameters(rabbitmq_host)
        )
        send_to_timeout_queue(timeout_connection, task)
        timeout_connection.close()
        return

    # If this is a timeout/OOM triage instance, but the bug is not a timeout/OOM, skip it
    if bug_type not in ["timeout", "out-of-memory"] and os.getenv("TIMEOUT_OOM_TRIAGE", "none") == "processor":
        return

    # Process and save the results of a TaskData to a DB pointed to by database_url.
    db_session = db.connect_database(database_url)

    try:
        # Create a unique key for the pentuple (using a hash to guard against special characters)
        pentuple_string = f"{task.task_id}:{harness}:{sanitizer}:{bug_type}:{trigger_point}"
        pentuple_hash = hashlib.md5(
            pentuple_string.encode('utf-8')).hexdigest()
        redis_key = f"triage:{task.task_id}:{pentuple_hash}"
        redis_key_lock = f"lock:triage:{task.task_id}:{pentuple_hash}"

        lock = redis.lock.Lock(get_redis_client(), redis_key_lock, timeout=600)
        if lock.acquire(blocking=True):
            try:
                # Check if this pentuple exists in Redis
                bug_profile_id = get_redis_client().get(redis_key)
                is_new_profile = bug_profile_id is None
                is_new_cluster = False

                if is_new_profile:
                    redis_new_profile_lock = f"lock:triage:{task.task_id}:new_profile"
                    new_profile_lock = redis.lock.Lock(
                        get_redis_client(), redis_new_profile_lock, timeout=600)
                    if new_profile_lock.acquire(blocking=True):
                        try:
                            # Pentuple not seen before; create a new bug profile in the database
                            new_profile_record = db.BugProfile(
                                task_id=task.task_id,
                                harness_name=harness,
                                sanitizer_bug_type=bug_type,
                                trigger_point=trigger_point,
                                summary=summary,
                                sanitizer=sanitizer
                            )
                            db_session.add(new_profile_record)
                            db_session.commit()  # This sets new_profile_record.id

                            bug_profile_id = new_profile_record.id

                            # Store the new bug profile id in Redis
                            get_redis_client().set(redis_key, bug_profile_id)
                            print(
                                f"[*] New bug profile created with id: {bug_profile_id}")
                            # log_triage(task.task_id, "found_new_bug_profile", target=task.project_name,
                            #            harness_name=harness, sanitizer=sanitizer,
                            #            bug_id=task.bug_id, bug_type=bug_type, trigger_point=trigger_point)

                            # HACKY: Insert to bug_groups using this new profile before deduplicating
                            # This ensures each bug_profile has at least 1 record in bug_groups,
                            # so that submitter can submit all bug_profiles
                            new_group_record = db.BugGroup(
                                bug_id=task.bug_id,
                                bug_profile_id=bug_profile_id,
                                diff_only=diff_only
                            )
                            db_session.add(new_group_record)
                            db_session.commit()
                            print(
                                f"[*] Bug group created for task {task.bug_id} with bug profile {bug_profile_id}")

                            # Deduplicate this new profile
                            cluster_id, is_new_cluster = do_dedup(
                                task, bug_profile_id, database_url,
                                storage_dir, model
                            )

                            # If this is a new cluster, add it to the task's list of bug clusters
                            if is_new_cluster:
                                bug_clusters = get_task_bug_clusters(
                                    task.task_id)
                                if cluster_id not in bug_clusters:
                                    bug_clusters.append(cluster_id)
                                    get_redis_client().hset(
                                        TASK_BUG_CLUSTERS_KEY, task.task_id, json.dumps(bug_clusters))
                                    print(
                                        f"[*] Added new bug cluster {cluster_id} to task {task.task_id}")
                                    # log_triage(task.task_id, "found_new_bug_cluster", target=task.project_name,
                                    #            harness_name=harness, sanitizer=sanitizer,
                                    #            bug_id=task.bug_id, bug_type=bug_type, trigger_point=trigger_point)

                        finally:
                            new_profile_lock.release()
                else:
                    bug_profile_id = int(bug_profile_id)
                    print(
                        f"[*] Using existing bug profile with id: {bug_profile_id}")

                    # Get the cluster ID for this profile
                    cluster_id = db.query_for_cluster_id(
                        bug_profile_id, database_url)

                # Get the smallest bug profile ID in this cluster
                smallest_profile_id = db.query_for_smallest_profile_id(
                    cluster_id, database_url)
                if smallest_profile_id:
                    # Create RabbitMQ connection for sending messages
                    patch_connection = pika.BlockingConnection(
                        pika.URLParameters(rabbitmq_host)
                    )

                    if smallest_profile_id != bug_profile_id or not is_new_profile:
                        # Insert a new bug group using smallest bug profile
                        new_group_record = db.BugGroup(
                            bug_id=task.bug_id,
                            bug_profile_id=smallest_profile_id,
                            diff_only=diff_only
                        )
                        db_session.add(new_group_record)
                        db_session.commit()
                        print(
                            f"[*] Bug group created for task {task.bug_id} with bug profile {smallest_profile_id}")

                    if is_new_cluster:
                        # For new clusters, send the smallest profile in this cluster to patch queue
                        # with patch_mode "generic" and high priority
                        for _ in range(3):
                            send_to_patch_queue(
                                patch_connection, smallest_profile_id, "generic", random.randint(8, 10))
                    else:
                        # For existing profiles, send all active smallest bug profiles in all bug clusters
                        send_active_task_bug_clusters(
                            patch_connection, database_url)

                    patch_connection.close()

            finally:
                lock.release()

    except Exception as e:
        db_session.rollback()
        print("Error occurred:", e)
        raise
    finally:
        db_session.close()


def log_broken_reports(task, output, state, storage_dir):
    log_dir = os.path.join(storage_dir, "logs", task.task_id, task.bug_id)
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, f"broken_output_{state}.txt"), "w") as log_file:
        log_file.write(output)


def listen_for_tasks(
    rabbitmq_host: str,
    queue_name: str,
    database_url: str,
    storage_dir: str,
    prefetch_count: int,
    model: str
):
    """
    Connect to RabbitMQ, listen for tasks in JSON format on `queue_name`,
    parse the message into a TaskData object, and process it.
    """

    # 1. Connect to RabbitMQ
    connection = pika.BlockingConnection(
        pika.URLParameters(rabbitmq_host)
    )
    channel = connection.channel()

    # 2. Make sure the queue exists (idempotent)
    channel.queue_declare(
        queue=queue_name,
        durable=True,
        arguments={"x-max-priority": 10}
    )

    # 3. Define a callback to process messages
    def callback(ch, method, properties, body, connection):
        try:
            data_dict = json.loads(body)

            diff = data_dict.get("diff", None)
            sanitizer = data_dict.get("sanitizer", "none")

            # Convert the JSON/dict to TaskData
            task = TaskData(
                bug_id=data_dict["bug_id"],
                task_id=data_dict["task_id"],
                task_type=data_dict["task_type"],
                sanitizer=sanitizer,
                harness_binary=data_dict["harness_name"],
                poc_path=data_dict["poc_path"],
                project_name=data_dict["project_name"],
                focus=data_dict["focus"],
                repo=data_dict["repo"],
                fuzz_tooling=data_dict["fuzzing_tooling"],
                diff=diff
            )

            print(f"[*] Received task: {task}")

            # Start a new thread for processing
            processing_thread = threading.Thread(
                target=process_task, args=(connection, ch, method, properties, body, task, rabbitmq_host))
            processing_thread.start()

        except Exception as e:
            print(f"[!] Failed to parse or process task: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def process_task(connection, ch, method, properties, body, task, rabbitmq_host):
        try:
            # Check if the task is still valid for processing
            task_status_key = f"global:task_status:{task.task_id}"
            task_status = get_redis_client().get(task_status_key)

            if task_status is not None and task_status.decode('utf-8') not in ["processing", "waiting"]:
                print(
                    f"[*] Task {task.task_id} is no longer active (status: {task_status}). Skipping processing for bug {task.bug_id}.")
                connection.add_callback_threadsafe(
                    lambda: ack_nack_message(ch, method.delivery_tag)
                )
                return

            if task.sanitizer == "*":
                for sanitizer in ["address", "memory", "undefined"]:
                    process_task_with_sanitizer(task, sanitizer)

            elif task.sanitizer not in ["address", "memory", "undefined", "thread", "none"]:
                print(
                    f"[!] Unrecognized sanitizer {task.sanitizer} for bug_id {task.bug_id}")
            else:
                process_task_with_sanitizer(task, task.sanitizer)

            cb = functools.partial(ack_nack_message, ch, method.delivery_tag)
            connection.add_callback_threadsafe(cb)
        except Exception as e:
            print(f"[!] Error processing bug {task.bug_id}: {e}")
            print(traceback.format_exc())

            # Retrieve the current retry count from message headers.
            retry_count = 0
            if properties.headers and "x-retry" in properties.headers:
                retry_count = properties.headers["x-retry"]

            if retry_count < 3:
                new_retry = retry_count + 1
                print(f"[!] Requeuing bug {task.bug_id}, attempt {new_retry}")
                # Create updated headers with the new retry count.
                new_headers = properties.headers.copy() if properties.headers else {}
                new_headers["x-retry"] = new_retry
                new_props = pika.BasicProperties(headers=new_headers)
                # Republish to the same queue (using queue_name from the parent scope)
                connection.add_callback_threadsafe(
                    lambda: ch.basic_publish(
                        exchange="",
                        routing_key=queue_name,
                        body=body,
                        properties=new_props
                    )
                )
            else:
                print(
                    f"[!] Bug {task.bug_id} failed after {retry_count} attempts. Not requeuing.")

            # In any case, acknowledge the original message so it is removed from the queue.
            connection.add_callback_threadsafe(
                lambda: ack_nack_message(ch, method.delivery_tag)
            )

    def process_task_with_sanitizer(task, sanitizer):
        if task.task_type == "full":
            # Build the project with the given sanitizer
            fuzz_tooling_path = build_project(
                task, sanitizer, storage_dir, False)
            # Discover all the harnesses, if it's a universal harness task
            if task.harness_binary == "*":
                harnesses = find_fuzzers(os.path.join(
                    fuzz_tooling_path, "build", "out", task.project_name))
            else:
                harnesses = [task.harness_binary]
            # Perform replay and triage over all required harness(es)
            print(f"[*] Triaging for harnesses: {harnesses}")
            for harness in harnesses:
                # Replay the PoC with the given harness
                replay_output, returncode = replay_poc(
                    fuzz_tooling=fuzz_tooling_path,
                    project_name=task.project_name,
                    harness_binary=harness,
                    poc_path=task.poc_path,
                )
                # Triage the output
                triage_full(task, sanitizer, harness,
                            replay_output, returncode)

        elif task.task_type == "delta":
            # Build the project's base state with the given sanitizer
            try:
                fuzz_tooling_path_unpatched = build_project(
                    task, sanitizer, storage_dir, False)
            except subprocess.CalledProcessError:
                # We don't care about a build fail on a repo's base state
                replay_output_unpatched = "failed to build"
                returncode_unpatched = 1
            # Build the project's delta state with the given sanitizer
            fuzz_tooling_path_patched = build_project(
                task, sanitizer, storage_dir, True)
            # Discover all the harnesses, if it's a universal harness task
            if task.harness_binary == "*":
                harnesses = find_fuzzers(os.path.join(
                    fuzz_tooling_path_patched, "build", "out", task.project_name))
            else:
                harnesses = [task.harness_binary]
            # Perform replay and triage over all required harness(es)
            print(f"[*] Triaging for harnesses: {harnesses}")
            for harness in harnesses:
                # Replay the PoC with the given harness on base state
                replay_output_unpatched, returncode_unpatched = replay_poc(
                    fuzz_tooling=fuzz_tooling_path_unpatched,
                    project_name=task.project_name,
                    harness_binary=harness,
                    poc_path=task.poc_path,
                )
                # Skip this bug entirely if the bug crashes base state
                # If logging is enabled, log the crash report if it's not parse-able
                if returncode_unpatched != 0:
                    print(
                        f"[*] Bug {task.bug_id} reproducible in base state, ignore")
                    if os.getenv("LOG_BROKEN_REPORT", None):
                        parser = JazzerSanitizerReport if "Java Exception" in replay_output_unpatched else UnifiedSanitizerReport
                        if not parser.parse(replay_output_unpatched):
                            log_broken_reports(
                                task, replay_output_unpatched, "base", storage_dir)
                    continue

                # Replay the PoC with the given harness on delta state
                replay_output_patched, returncode_patched = replay_poc(
                    fuzz_tooling=fuzz_tooling_path_patched,
                    project_name=task.project_name,
                    harness_binary=harness,
                    poc_path=task.poc_path,
                )

                # If logging is enabled, log the crash report if it's not parse-able
                if returncode_patched != 0:
                    if os.getenv("LOG_BROKEN_REPORT", None):
                        parser = JazzerSanitizerReport if "Java Exception" in replay_output_patched else UnifiedSanitizerReport
                        if not parser.parse(replay_output_patched):
                            log_broken_reports(
                                task, replay_output_patched, "delta", storage_dir)

                # Triage the outputs
                triage_delta(task, sanitizer, harness,
                             replay_output_unpatched, returncode_unpatched,
                             replay_output_patched, returncode_patched)

    def triage_full(task, sanitizer, harness, replay_output, returncode):
        if "Java Exception" in replay_output:
            parser = JazzerSanitizerReport
        else:
            parser = UnifiedSanitizerReport

        if returncode == 0:
            print(
                f"[!] Unable to get a crash from replaying the PoC for bug_id {task.bug_id}")
        else:
            report = parser.parse(replay_output)

            if not report:
                print(
                    f"[!] Unable to get a crash report from replaying the PoC for bug_id {task.bug_id}")
            else:
                print(f"[*] Triage result:")
                print(f"- Bug type: {report.cwe}")
                print(f"- Trigger point: {report.trigger_point}")
                dedup_and_update_db(
                    task, sanitizer, harness, database_url,
                    report.cwe, report.trigger_point, report.summary,
                    False, rabbitmq_host, storage_dir, model
                )
                print(
                    f"[*] Bug triage finished for bug_id {task.bug_id}")

    def triage_delta(task, sanitizer, harness,
                     replay_output_unpatched, returncode_unpatched,
                     replay_output_patched, returncode_patched):
        if "Java Exception" in replay_output_patched:
            parser = JazzerSanitizerReport
        else:
            parser = UnifiedSanitizerReport

        if returncode_patched == 0:
            print(
                f"[!] Unable to get a crash from replaying the PoC for bug_id {task.bug_id}")
        else:
            report_unpatched = parser.parse(replay_output_unpatched)
            report_patched = parser.parse(replay_output_patched)

            if not report_patched:
                print(
                    f"[!] Unable to get a crash report from replaying the PoC for bug_id {task.bug_id}")
            else:
                if returncode_unpatched == 0:
                    diff_only = True
                    print(f"[*] Triage result:")
                    print(f"- Bug type: {report_patched.cwe}")
                    print(f"- Trigger point: {report_patched.trigger_point}")
                    print(f"- Trigger on diff only: {diff_only}")
                    dedup_and_update_db(
                        task, sanitizer, harness, database_url,
                        report_patched.cwe, report_patched.trigger_point, report_patched.summary,
                        diff_only, rabbitmq_host, storage_dir, model
                    )
                    print(
                        f"[*] Bug triage finished for bug_id {task.bug_id}")
                else:
                    diff_only = False
                    print(
                        f"[*] Bug {task.bug_id} reproducible in base state, ignore")

    def ack_nack_message(channel, delivery_tag, nack=False):
        if channel.is_open:
            if nack:
                channel.basic_nack(delivery_tag, requeue=False)
            else:
                channel.basic_ack(delivery_tag)
        else:
            raise pika.exceptions.StreamLostError

    # 4. Start consuming messages
    channel.basic_qos(prefetch_count=prefetch_count)
    on_message_callback = functools.partial(callback, connection=connection)
    channel.basic_consume(
        queue=queue_name,
        on_message_callback=on_message_callback
    )

    print("[*] Listening for tasks. Press CTRL+C to exit.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("[*] Stopping consumer...")
        channel.stop_consuming()
        connection.close()


if __name__ == "__main__":
    # Retrieve configuration from environment variables with default values
    rabbitmq_host = os.environ.get("RABBITMQ_HOST", "http://localhost:5672")
    queue_name = os.environ.get("QUEUE_NAME", "triage_queue")
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://user:password@localhost/mydatabase"
    )
    redis_sentinel_hosts = os.environ.get(
        "REDIS_SENTINEL_HOSTS",
        "localhost:26379"
    )
    redis_master = os.environ.get(
        "REDIS_MASTER",
        "mymaster"
    )
    redis_password = os.environ.get(
        "REDIS_PASSWORD",
        None
    )
    storage_dir = os.environ.get(
        "STORAGE_DIR",
        "/crs"
    )
    otel_endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://localhost:4317"
    )
    otel_headers = os.getenv(
        "OTEL_EXPORTER_OTLP_HEADERS",
        ""
    )
    otel_protocol = os.getenv(
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "grpc"
    )
    prefetch_count = int(os.environ.get("PREFETCH_COUNT", 8))
    model = os.environ.get("DEDUP_MODEL", "o4-mini")

    # Optional: Print configurations for debugging purposes
    print("Configuration:")
    print(f"  RabbitMQ Host: {rabbitmq_host}")
    print(f"  Queue Name: {queue_name}")
    print(f"  Database URL: {database_url}")
    print(f"  Redis Sentinel hosts: {redis_sentinel_hosts}")
    print(f"  Redis Master: {redis_master}")
    print(f"  Redis Password: {redis_password}")
    print(f"  Storage dir: {storage_dir}")
    print(f"  OTEL endpoint: {otel_endpoint}")
    print(f"  Prefetch count: {prefetch_count}")
    print(f"  Dedup Model: {model}")

    redis_sentinel_hosts = [
        (h, int(p)) for h, p in (item.split(":") for item in redis_sentinel_hosts.split(","))]
    init_redis(redis_sentinel_hosts, redis_master, password=redis_password)
    init_opentelemetry(otel_endpoint, otel_headers, otel_protocol, "triage")

    cleanup_containers("triage_runner")

    # Start listening for tasks with the given args
    listen_for_tasks(
        rabbitmq_host=rabbitmq_host,
        queue_name=queue_name,
        database_url=database_url,
        storage_dir=storage_dir,
        prefetch_count=prefetch_count,
        model=model
    )
