import os
import traceback
import pika.exceptions
import requests
import tarfile
import shutil
import subprocess
import json
import threading
import functools
from dataclasses import dataclass
from typing import List
from datetime import datetime, UTC
from opentelemetry import trace, context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

import pika

from grabber import grab_corpus
from infra.oss_fuzz import compile_project, find_fuzzers

import utils.db as db
from utils.telemetry import init_opentelemetry, get_task_span, start_span_with_crs_inheritance
from utils.redis import init_redis


@dataclass
class TaskData:
    task_id: int
    task_type: str
    project_name: str
    focus: str
    repo: List[str]         # A list of URLs to .tar.gz files
    fuzz_tooling: str       # A URL to a .tar.gz file
    diff: str               # Another URL to a .tar.gz file


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

        # Extract all files
        tar.extractall(path=dest_dir)

    # If there's exactly one top-level directory, return it
    if len(top_level_dirs) == 1:
        return top_level_dirs.pop()

    return None


def prepare_repos(task: TaskData):
    # Create a directory for this task
    task_dir = os.path.abspath(os.path.join(
        ".tmp", "tasks", str(task.task_id)))
    os.makedirs(task_dir, exist_ok=True)

    # Extract repos
    extracted_repos = []
    for repo_path in task.repo:
        folder_name = extract_from_storage(repo_path, task_dir)
        extracted_repos.append(folder_name)

    # Extract fuzz_tooling
    fuzz_tooling_dir = extract_from_storage(task.fuzz_tooling, task_dir)

    # Extract diff
    diff_dir = extract_from_storage(task.diff, task_dir)

    print("[*] All archives have been extracted.")
    print(f"- Task directory: {task_dir}")
    print(f"- Repo directories extracted: {extracted_repos}")
    print(f"- Fuzz tooling extracted into: {fuzz_tooling_dir}")
    print(f"- Diff extracted into: {diff_dir}")

    # Apply the diff files
    if diff_dir:
        diff_path = os.path.join(task_dir, diff_dir)
        apply_diff_command = ["patch", "--batch", "--no-backup-if-mismatch", "-p1"]
        
        if os.path.isfile(diff_path) and (diff_path.endswith('.patch') or diff_path.endswith('.diff')):
            # diff_dir is a file, so apply it directly
            with open(diff_path, "rb") as patch_file:
                subprocess.run(apply_diff_command, stdin=patch_file, check=True, cwd=os.path.join(task_dir, task.focus))
            print(f"[+] Applied diff from {diff_path} to {os.path.join(task_dir, task.focus)}")
        
        elif os.path.isdir(diff_path):
            # diff_dir is a directory, so iterate over contained patch/diff files
            diff_files = [f for f in os.listdir(diff_path) if f.endswith('.patch') or f.endswith('.diff')]
            for diff_file in diff_files:
                diff_file_path = os.path.join(diff_path, diff_file)
                if os.path.exists(diff_file_path):
                    with open(diff_file_path, "rb") as patch_file:
                        subprocess.run(apply_diff_command, stdin=patch_file, check=True, cwd=os.path.join(task_dir, task.focus))
                    print(f"[+] Applied diff from {diff_file_path} to {os.path.join(task_dir, task.focus)}")
                else:
                    print(f"[!] Diff file {diff_file_path} does not exist")
        else:
            print(f"[!] The provided diff path {diff_path} is neither a valid file nor a directory.")

    return task_dir, fuzz_tooling_dir

    return grab_corpus(
        project_name=task.project_name,
        src_dir=os.path.join(task_dir, task.focus),
        fuzz_tooling_dir=os.path.join(task_dir, fuzz_tooling_dir),
        task_dir=task_dir
    )


def save_result_to_db(task: TaskData, storage_dir: str, database_url: str):
    """
    Save the results of a TaskData to a DB pointed to by database_url,
    storing seeds in storage_dir.
    """
    db_session = db.connect_database(database_url)

    task_corpus_dir = os.path.abspath(os.path.join(
        ".tmp", "tasks", str(task.task_id), "corpus"))

    try:
        # Compress and copy corpus to shared volume
        corpus_storage_dir = os.path.join(
            storage_dir, "corpus", str(task.task_id))
        os.makedirs(corpus_storage_dir, exist_ok=True)
        corpus_tar_gz_path = os.path.join(corpus_storage_dir, f"corpus_{
                                        task.task_id}.tar.gz")
        with tarfile.open(corpus_tar_gz_path, "w:gz") as tar:
            tar.add(task_corpus_dir, arcname=".")

        # Create DB record
        new_seed_record = db.Seed(
            task_id=str(task.task_id),  # Ensure string
            path=corpus_tar_gz_path,
            harness_name="*",
            fuzzer="corpus",
            coverage=0,
            metric=None
        )
        db_session.add(new_seed_record)
        db_session.commit()

        return corpus_tar_gz_path
    except Exception as e:
        db_session.rollback()
        print("Error occurred:", e)
        raise
    finally:
        db_session.close()


def save_bugs_to_db(task: TaskData, sanitizers, harnesses, storage_dir: str, database_url: str):
    db_session = db.connect_database(database_url)

    task_corpus_dir = os.path.abspath(os.path.join(
        ".tmp", "tasks", str(task.task_id), "corpus"))

    try:
        corpus_storage_dir = os.path.join(
            storage_dir, "corpus", str(task.task_id))
        os.makedirs(corpus_storage_dir, exist_ok=True)
        
        # Get all files in the corpus directory
        corpus_files = []
        for root, _, files in os.walk(task_corpus_dir):
            for file in files:
                corpus_files.append(os.path.join(root, file))
        
        # Copy each file to the storage directory and create bug records
        for file_path in corpus_files:
            # Get relative path from task_corpus_dir
            rel_path = os.path.relpath(file_path, task_corpus_dir)
            # Create destination path
            dest_path = os.path.join(corpus_storage_dir, rel_path)
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            # Copy the file
            shutil.copy2(file_path, dest_path)
            
            # Create a bug record for each sanitizer and harness combination
            for sanitizer in sanitizers:
                for harness in harnesses:
                    new_bug = db.Bug(
                        task_id=str(task.task_id),
                        architecture="x86_64",  # Default architecture
                        poc=dest_path,
                        harness_name=harness,
                        sanitizer=sanitizer,
                        sarif_report=None  # No SARIF report for now
                    )
                    db_session.add(new_bug)
        
        # Commit all the bug records
        db_session.commit()
        print(f"[+] Saved {len(corpus_files) * len(sanitizers) * len(harnesses)} bug records for task {task.task_id}")
        
    except Exception as e:
        db_session.rollback()
        print(f"[!] Error saving bugs to DB: {e}")
        print(traceback.format_exc())
        raise
    finally:
        db_session.close()


def send_to_cmin_queue(
    connection: pika.BlockingConnection,
    task: TaskData,
    harness_name: str,
    corpus_path: str
):
    try:
        channel = connection.channel()

        # Declare the queue with priority support
        channel.queue_declare(
            queue="cmin_queue",
            durable=True
        )

        # Create the message
        message = json.dumps({
            "task_id": task.task_id,
            "harness": harness_name,
            "seeds": corpus_path
        })

        # Publish the message with the specified priority
        channel.basic_publish(
            exchange="",
            routing_key="cmin_queue",
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2
            )
        )

        print(
            f"[*] Sent corpus {corpus_path} to cmin_queue")

    except Exception as e:
        print(f"[!] Failed to send to cmin_queue: {e}")


def listen_for_tasks(
    rabbitmq_host: str,
    queue_name: str,
    database_url: str,
    storage_dir: str,
    prefetch_count: int
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
        durable=True
    )

    # 3. Define a callback to process messages
    def callback(ch, method, properties, body, connection):
        try:
            data_dict = json.loads(body)

            diff = data_dict.get("diff", None)

            # Convert the JSON/dict to TaskData
            task = TaskData(
                task_id=data_dict["task_id"],
                task_type=data_dict["task_type"],
                project_name=data_dict["project_name"],
                focus=data_dict["focus"],
                repo=data_dict["repo"],
                fuzz_tooling=data_dict["fuzzing_tooling"],
                diff=diff
            )

            print(f"[*] Received task: {task}")

            # Start a new thread for processing
            processing_thread = threading.Thread(
                target=process_task, args=(connection, ch, method, properties, body, task))
            processing_thread.start()

        except Exception as e:
            print(f"[!] Failed to parse task: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def process_task(connection, ch, method, properties, body, task):
        # Retrieve global task span from redis
        payload = get_task_span(task.task_id)
        if payload:
            propagator = TraceContextTextMapPropagator()
            parent_context = propagator.extract(json.loads(payload))
            token = context.attach(parent_context)
        else:
            token = None
            
        try:
            # Retrieve the current retry count from message headers.
            retry_count = 0
            if properties.headers and "x-retry" in properties.headers:
                retry_count = properties.headers["x-retry"]
            with start_span_with_crs_inheritance(
                f"attempt #{retry_count+1}",
                attributes={
                    "crs.action.category": "input_generation",
                    "crs.action.name": "grab_fuzzing_corpus",
                    "crs.action.target": task.project_name
                }
            ) as process_span:
                try:
                    # Extract and prepare the repo + fuzz tooling
                    task_dir, fuzz_tooling_dir = prepare_repos(task)
                    # Grab corpus and save to db
                    if grab_corpus(
                        project_name=task.project_name,
                        src_dir=os.path.join(task_dir, task.focus),
                        fuzz_tooling_dir=os.path.join(task_dir, fuzz_tooling_dir),
                        task_dir=task_dir
                    ):
                        with start_span_with_crs_inheritance(
                            f"save to database"
                        ):
                            corpus_path = save_result_to_db(task, storage_dir, database_url)
                            print(f"[*] Corpus stored in DB for task {task.task_id}")

                        # Now build the project and find all harnesses in it
                        with start_span_with_crs_inheritance(
                            f"build project"
                        ):
                            compile_project(
                                fuzz_tooling=os.path.join(task_dir, fuzz_tooling_dir),
                                project_name=task.project_name,
                                sanitizer=None,
                                src_path=os.path.join(task_dir, task.focus)
                            )
                        harnesses, sanitizers, is_java = find_fuzzers(task.project_name, os.path.join(task_dir, fuzz_tooling_dir))
                        # Send corpus to cmin if it's not a java task
                        if not is_java:
                            with start_span_with_crs_inheritance(
                                f"send to cmin",
                                attributes={
                                    "crs.action.target.harnesses": harnesses
                                }
                            ):
                                for harness in harnesses:
                                    cmin_connection = pika.BlockingConnection(
                                        pika.URLParameters(rabbitmq_host)
                                    )
                                    send_to_cmin_queue(cmin_connection, task, harness, corpus_path)
                                    cmin_connection.close()
                        
                        # Save each corpus seed to DB for triage
                        with start_span_with_crs_inheritance(
                            f"send to triage",
                            attributes={
                                "crs.action.target.harnesses": harnesses,
                                "crs.action.target.sanitizers": sanitizers
                            }
                        ):
                            if harnesses:
                                save_bugs_to_db(task, sanitizers, harnesses, storage_dir, database_url)
                    else:
                        print(f"[*] No corpus found for task {task.task_id}")
                    cb = functools.partial(ack_nack_message, ch, method.delivery_tag)
                    connection.add_callback_threadsafe(cb)
                except Exception as e:
                    print(f"[!] Error processing task {task.task_id}: {e}")
                    print(traceback.format_exc())

                    # Retrieve the current retry count from message headers.
                    retry_count = 0
                    if properties.headers and "x-retry" in properties.headers:
                        retry_count = properties.headers["x-retry"]

                    if retry_count < 3:
                        new_retry = retry_count + 1
                        print(f"[!] Requeuing task {task.task_id}, attempt {new_retry}")
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
                        print(f"[!] Task {task.task_id} failed after {retry_count} attempts. Not requeuing.")

                    # In any case, acknowledge the original message so it is removed from the queue.
                    connection.add_callback_threadsafe(
                        lambda: ack_nack_message(ch, method.delivery_tag)
                    )
        finally:
            if token:
                context.detach(token)

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
    queue_name = os.environ.get("QUEUE_NAME", "corpus_queue")
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
    storage_dir = os.environ.get("STORAGE_DIR", "/crs")
    prefetch_count = int(os.environ.get("PREFETCH_COUNT", 15))

    # Optional: Print configurations for debugging purposes
    print("Configuration:")
    print(f"  RabbitMQ Host: {rabbitmq_host}")
    print(f"  Queue Name: {queue_name}")
    print(f"  Database URL: {database_url}")
    print(f"  Redis Sentinel hosts: {redis_sentinel_hosts}")
    print(f"  Redis Master: {redis_master}")
    print(f"  Redis Password: {redis_password}")
    print(f"  OTEL endpoint: {otel_endpoint}")
    print(f"  Storage Directory: {storage_dir}")
    print(f"  Prefetch count: {prefetch_count}")

    redis_sentinel_hosts = [
        (h, int(p)) for h, p in (item.split(":") for item in redis_sentinel_hosts.split(","))]
    init_redis(redis_sentinel_hosts, redis_master, password=redis_password)
    init_opentelemetry(otel_endpoint, otel_headers, otel_protocol, "corpus_grabber")

    # Start listening for tasks with the given args
    listen_for_tasks(
        rabbitmq_host=rabbitmq_host,
        queue_name=queue_name,
        database_url=database_url,
        storage_dir=storage_dir,
        prefetch_count=prefetch_count
    )
