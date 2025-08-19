#!/opt/venv/bin/python

import base64
import json
import random
import time
import uuid
from hashlib import sha256
from pathlib import Path
from typing import Optional

import pika
import pika.exceptions
import yaml
from sqlalchemy import func

from aixcc.db import (
    Base,
    Bug,
    BugGroup,
    BugProfile,
    Message,
    Patch,
    PatchBug,
    Source,
    SourceTypeEnum,
    Task,
    TaskStatusEnum,
    TaskTypeEnum,
    User,
    make_session,
)
from aixcc.env import DB_URL
from patch_generator.env import (
    MOCK_MODE,
    MOCK_MODEL,
    RABBITMQ_PATCH_PRIORITY,
    RABBITMQ_PATCH_QUEUE,
    RABBITMQ_URL,
)
from patch_generator.logger import logger


def mock_full(folder: str, patch_mode: Optional[str] = None) -> None:
    with make_session() as session:
        user = User(username="test", password="test")
        message = Message(
            id=str(uuid.uuid4()),
            message_time=int(time.time()),
        )

        session.add_all([user, message])
        for path in Path(f"/testcases/{folder}").iterdir():
            project = path.name.rsplit("-", 1)[0]
            source = path / "source.tar.gz"
            fuzz_tooling = path / "fuzz_tooling.tar.gz"
            if not source.is_file() or not fuzz_tooling.is_file():
                continue

            diff = path / "diff.tar.gz"

            task = Task(
                id=str(uuid.uuid4()),
                user=user,
                message=message,
                deadline=int(time.time() + 3600),
                focus=project,
                project_name=project,
                task_type=TaskTypeEnum.delta if diff.is_file() else TaskTypeEnum.full,
                status=TaskStatusEnum.processing,
                metadata_={"mock_mode": MOCK_MODE},
            )
            repo_source = Source(
                task_id=task.id,
                sha256=sha256(source.read_bytes()).hexdigest(),
                source_type=SourceTypeEnum.repo,
                url="http://fake-server:8000/oss-fuzz/source.tar.gz",
                path=source.as_posix(),
            )
            fuzz_tooling_source = Source(
                task_id=task.id,
                sha256=sha256(fuzz_tooling.read_bytes()).hexdigest(),
                source_type=SourceTypeEnum.fuzz_tooling,
                url="http://fake-server:8000/oss-fuzz/fuzz_tooling.tar.gz",
                path=fuzz_tooling.as_posix(),
            )
            session.add_all([task, repo_source, fuzz_tooling_source])
            if diff.is_file():
                diff_source = Source(
                    task_id=task.id,
                    sha256=sha256(diff.read_bytes()).hexdigest(),
                    source_type=SourceTypeEnum.diff,
                    url="http://fake-server:8000/oss-fuzz/diff.tar.gz",
                    path=diff.as_posix(),
                )
                session.add(diff_source)

            for bug_path in path.glob("OSV-*"):
                osv_yaml = bug_path / "osv.yaml"
                if not osv_yaml.is_file():
                    continue

                osv_data = yaml.safe_load(osv_yaml.read_text())
                bug_profile = BugProfile(
                    task_id=task.id,
                    harness_name=osv_data["harness_name"],
                    sanitizer="none",
                    sanitizer_bug_type=bug_path.name,
                    trigger_point="",
                    summary="",
                )
                session.add(bug_profile)

                all_bugs = []
                for _ in range(random.randint(10, 20)):
                    bug = Bug(
                        task_id=task.id,
                        architecture="x86_64",
                        poc=(bug_path / "poc.bin").as_posix(),
                        harness_name=osv_data["harness_name"],
                        sanitizer="none",
                    )
                    bug_group = BugGroup(
                        bug=bug,
                        bug_profile=bug_profile,
                    )
                    all_bugs.append(bug)
                    session.add_all([bug, bug_group])

                patch_dir = Path("/testcases") / f"{folder}-patch" / "data" / bug_path.name
                if patch_dir.is_dir():
                    for diff in patch_dir.glob("*.diff"):
                        if patch_mode == "all" or (patch_mode == "random" and random.random() < 0.5):
                            _, model = diff.stem.split("-", 1)
                            if model == MOCK_MODEL or MOCK_MODEL == "all":
                                patch = Patch(
                                    bug_profile=bug_profile,
                                    patch=base64.b64encode(diff.read_bytes()).decode(),
                                    model=model,
                                )
                                session.add(patch)
                                for bug in all_bugs:
                                    if patch_mode == "all" or (patch_mode == "random" and random.random() < 0.9):
                                        session.add(
                                            PatchBug(
                                                patch=patch,
                                                bug=bug,
                                                repaired=True,
                                            )
                                        )
        session.commit()


def mock_replay(folder: str) -> None:
    with make_session() as session:
        user = User(username="test", password="test")
        message = Message(
            id=str(uuid.uuid4()),
            message_time=int(time.time()),
        )

        session.add_all([user, message])
        for path in Path(f"/testcases/{folder}").iterdir():
            project = path.name.rsplit("-", 1)[0]
            source = path / "source.tar.gz"
            fuzz_tooling = path / "fuzz_tooling.tar.gz"
            if not source.is_file() or not fuzz_tooling.is_file():
                continue

            diff = path / "diff.tar.gz"
            task = Task(
                id=str(uuid.uuid4()),
                user=user,
                message=message,
                deadline=int(time.time() + 3600),
                focus=project,
                project_name=project,
                task_type=TaskTypeEnum.delta if diff.is_file() else TaskTypeEnum.full,
                status=TaskStatusEnum.processing,
                metadata_={"mock_mode": MOCK_MODE},
            )
            repo_source = Source(
                task_id=task.id,
                sha256=sha256(source.read_bytes()).hexdigest(),
                source_type=SourceTypeEnum.repo,
                url="http://fake-server:8000/oss-fuzz/source.tar.gz",
                path=source.as_posix(),
            )
            fuzz_tooling_source = Source(
                task_id=task.id,
                sha256=sha256(fuzz_tooling.read_bytes()).hexdigest(),
                source_type=SourceTypeEnum.fuzz_tooling,
                url="http://fake-server:8000/oss-fuzz/fuzz_tooling.tar.gz",
                path=fuzz_tooling.as_posix(),
            )
            session.add_all([task, repo_source, fuzz_tooling_source])
            if diff.is_file():
                diff_source = Source(
                    task_id=task.id,
                    sha256=sha256(diff.read_bytes()).hexdigest(),
                    source_type=SourceTypeEnum.diff,
                    url="http://fake-server:8000/oss-fuzz/diff.tar.gz",
                    path=diff.as_posix(),
                )
                session.add(diff_source)

            for bug_path in path.glob("OSV-*"):
                osv_yaml = bug_path / "osv.yaml"
                if not osv_yaml.is_file():
                    continue

                osv_data = yaml.safe_load(osv_yaml.read_text())

                patch_dir = Path("/testcases") / f"{folder}-patch" / "data" / bug_path.name
                if patch_dir.is_dir():
                    for diff in patch_dir.glob("*.diff"):
                        _, model = diff.stem.split("-", 1)
                        bug_profile = BugProfile(
                            task_id=task.id,
                            harness_name=osv_data["harness_name"],
                            sanitizer="none",
                            sanitizer_bug_type=bug_path.name,
                            trigger_point="",
                            summary=diff.read_text(),
                        )
                        session.add(bug_profile)

                        if model == MOCK_MODEL or MOCK_MODEL == "all":
                            session.add(
                                Patch(
                                    bug_profile=bug_profile,
                                    patch=base64.b64encode(diff.read_bytes()).decode(),
                                    model=model,
                                )
                            )

                        for _ in range(5):
                            bug = Bug(
                                task_id=task.id,
                                architecture="x86_64",
                                poc=(bug_path / "poc.bin").as_posix(),
                                harness_name=osv_data["harness_name"],
                                sanitizer="none",
                            )
                            bug_group = BugGroup(
                                bug=bug,
                                bug_profile=bug_profile,
                            )
                            session.add_all([bug, bug_group])
        session.commit()


def setup_database() -> None:
    assert DB_URL == "postgresql://root:root@aixcc-postgres:5432/dataisland"
    with make_session() as session:
        Base.metadata.drop_all(bind=session.get_bind())
        Base.metadata.create_all(bind=session.get_bind())

    assert MOCK_MODE.count("-") == 1, f"Invalid MOCK_MODE: {MOCK_MODE}"
    folder, mode = MOCK_MODE.split("-")

    match mode:
        case "replay":
            mock_replay(folder)
        case "fresh":
            mock_full(folder)
        case "full":
            mock_full(folder, patch_mode="all")
        case "hybrid":
            mock_full(folder, patch_mode="random")


def setup_rabbitmq() -> None:
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            break
        except pika.exceptions.AMQPConnectionError:
            logger.info("[❌] RabbitMQ is not ready yet, retrying in 5 seconds")
            time.sleep(5)

    channel = connection.channel()
    channel.queue_declare(
        queue=RABBITMQ_PATCH_QUEUE,
        durable=True,
        arguments={"x-max-priority": RABBITMQ_PATCH_PRIORITY},
    )

    channel.queue_purge(queue=RABBITMQ_PATCH_QUEUE)

    mode = MOCK_MODE.split("-")[-1]
    with make_session() as session:
        for bug_profile in session.query(BugProfile).order_by(func.random()).all():
            channel.basic_publish(
                exchange="",
                routing_key=RABBITMQ_PATCH_QUEUE,
                body=json.dumps(
                    {
                        "bug_profile_id": bug_profile.id,
                        "patch_mode": "none" if mode == "replay" else "generic",
                    }
                ),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    priority=RABBITMQ_PATCH_PRIORITY,
                ),
            )


if __name__ == "__main__":
    setup_database()
    setup_rabbitmq()
