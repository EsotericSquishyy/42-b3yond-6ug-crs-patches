import base64
import random
import shutil
import traceback
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

from sqlalchemy.exc import IntegrityError

from aixcc.db import (
    BugGroup,
    BugProfile,
    BugProfileStatus,
    Patch,
    PatchBug,
    PatchDebug,
    SubmissionStatusEnum,
    Task,
    TaskStatusEnum,
    make_session,
)
from aixcc.utils import search_available_patch_query
from patch_generator.builder import AIXCCBuilder, create_builder
from patch_generator.env import MODEL
from patch_generator.logger import logger
from patch_generator.telemetry import TelemetryContext
from patchagent.agent.generator import agent_generator
from patchagent.builder import OSSFuzzPoC
from patchagent.lang import Lang
from patchagent.task import PatchTask, ValidationResult


class PatchMode(Enum):
    generic = "generic"
    fast = "fast"
    none = "none"

    @staticmethod
    def from_str(mode: Any) -> "PatchMode":
        match mode:
            case "fast":
                return PatchMode.fast
            case "none":
                return PatchMode.none
            case _:
                return PatchMode.generic


def is_available_bug_profile(bug_profile_id: int) -> bool:
    with make_session() as session:
        if (
            session.query(BugProfileStatus)
            .filter_by(
                bug_profile_id=bug_profile_id,
                status=SubmissionStatusEnum.failed,
            )
            .count()
            > 0
        ):
            return False

        bug_profile = session.query(BugProfile).filter_by(id=bug_profile_id).one()
        task: Task = bug_profile.task

        if task.status not in [TaskStatusEnum.processing, TaskStatusEnum.waiting]:
            return False

        group_size = session.query(BugGroup).filter_by(bug_profile_id=bug_profile_id).count()
        for patch in search_available_patch_query(session, bug_profile_id).all():
            if session.query(PatchBug).filter_by(patch_id=patch.id, repaired=True).count() == group_size:
                return False

        return True


def log_event(event: str, description: str) -> None:
    with make_session() as session:
        session.add(PatchDebug(event=event, description=description))
        session.commit()

    logger.info(description)


def copy_poc_to_builder(pocs: List[OSSFuzzPoC], builder: AIXCCBuilder) -> List[OSSFuzzPoC]:
    workspace = builder.workspace / "pocs"
    shutil.rmtree(workspace, ignore_errors=True)

    workspace.mkdir(parents=True, exist_ok=True)

    new_pocs = []
    for id, poc in enumerate(pocs):
        new_poc_path = workspace / f"poc-{id}"
        shutil.copy(poc.path, new_poc_path)
        new_pocs.append(OSSFuzzPoC(new_poc_path, poc.harness_name))

    return new_pocs


def repair_internal(bug_profile_id: int, patch_mode: PatchMode) -> Optional[int]:
    log_event("processing", f"[🛠️] Processing {bug_profile_id}")

    with make_session() as session:
        bug_profile = session.query(BugProfile).filter_by(id=bug_profile_id).one()

        builder = create_builder(bug_profile.task.id)

        bugs = [bg.bug for bg in bug_profile.bug_groups]
        random.shuffle(bugs)

        bug_ids = {bug.id for bug in bugs}

        for patch in search_available_patch_query(session, bug_profile_id).all():
            for bug in bugs:
                if session.query(PatchBug).filter_by(bug_id=bug.id, patch_id=patch.id).count() == 0:
                    raw_patch = base64.b64decode(patch.patch).decode()
                    result, report = PatchTask(
                        copy_poc_to_builder([OSSFuzzPoC(Path(bug.poc), bug.harness_name)], builder),
                        builder,
                    ).validate(raw_patch)

                    if result not in [
                        ValidationResult.BugFree,
                        ValidationResult.BugDetected,
                    ]:
                        # This situation should not occur under normal circumstances,
                        # but may happen if the system is unstable. We'll skip this patch
                        # and retry when the system stabilizes.
                        log_event("unstable", f"[🫠🫠🫠] Fail to reuse the patch {patch.id} due to {result.value}: {report}")
                        return None

                    if result == ValidationResult.BugDetected and patch_mode == PatchMode.none:
                        log_event("fixme", f"[🐞🐞🐞] Bug profile {bug_profile_id} is detected: {report}")

                    repaired = result == ValidationResult.BugFree
                    try:
                        session.add(PatchBug(bug_id=bug.id, patch=patch, repaired=repaired))
                        session.commit()
                    except IntegrityError:
                        session.rollback()

                    if not repaired:
                        break
            else:
                # NOTE: This else block is part of the for loop.
                # This else block is executed if the loop did NOT break.
                # This means that the patch is valid for all bugs.
                logger.info(f"[✅] Patch is found for {bug_profile_id} from the database")
                return None

        pocs: List[OSSFuzzPoC] = [OSSFuzzPoC(Path(bug.poc), bug.harness_name) for bug in bugs]
        patchtask = PatchTask(copy_poc_to_builder(pocs, builder), builder)

    if patchtask.builder.language not in [Lang.CLIKE, Lang.JVM]:
        logger.info("[❌] Patch agent does not support the language")
        return None

    init_result, init_report = patchtask.initialize()

    if init_result not in [ValidationResult.BugDetected, ValidationResult.BugFree]:
        log_event("unstable", f"[🫠🫠🫠] Fail to reproduce bug profile {bug_profile_id} due to {init_result.value}: {init_report}")
        return None

    if init_result == ValidationResult.BugFree:
        log_event("fixme", f"[🐞🐞🐞] Bug profile {bug_profile_id} do not trigger any crash")
        return None

    log_event(f"repairing-{patch_mode.value}", f"Repairing {bug_profile_id} with patch agent:\n\n{patchtask.report.summary}")

    match patch_mode:
        case PatchMode.generic:
            logger.info(f"[🐢🐢🐢] Start processing {bug_profile_id} with generic agent")
            patch = patchtask.repair(
                agent_generator(
                    model=MODEL,
                    fast=False,
                    stop_indicator=lambda: not is_available_bug_profile(bug_profile_id),
                )
            )
        case PatchMode.fast:
            logger.info(f"[🐇🐇🐇] Start processing {bug_profile_id} with fast agent")
            patch = patchtask.repair(
                agent_generator(
                    model=MODEL,
                    fast=True,
                    stop_indicator=lambda: not is_available_bug_profile(bug_profile_id),
                )
            )
        case PatchMode.none:
            assert patchtask.builder.language_server is not None
            logger.info("[🤡🤡🤡] Skip patch (Mock mode only!!!)")
            return None

    if patch is not None:
        logger.debug(f"[✅] Patch Generated:\n\n{patch}")
        logger.info(f"[✅] Patch is found for {bug_profile_id} by patch agent")
        with make_session() as session:
            patch = Patch(bug_profile_id=bug_profile_id, patch=base64.b64encode(patch.encode()).decode(), model=MODEL)
            session.add(patch)
            session.add_all([PatchBug(bug_id=id, patch=patch, repaired=True) for id in bug_ids])
            session.commit()
            return patch.id
    else:
        logger.info(f"[❌] Patch is not found for {bug_profile_id}")
        return None


def repair(bug_profile_id: int, patch_mode: PatchMode) -> Optional[int]:
    try:
        with make_session() as session:
            task_id = session.query(BugProfile).filter_by(id=bug_profile_id).one().task_id
        with TelemetryContext(task_id):
            return repair_internal(bug_profile_id, patch_mode)
    except Exception as e:
        log_event(e.__class__.__name__, f"[🚨] {e.__class__.__name__} occurred during processing {bug_profile_id} {traceback.format_exc()}")
        raise
