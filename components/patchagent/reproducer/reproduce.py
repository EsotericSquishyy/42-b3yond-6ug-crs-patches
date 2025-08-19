import base64
import hashlib
import shutil
import time
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import List

from build_utils import (
    SANITIZER_MAP,
    ReproBuilder,
    copy_poc_to_builder,
    create_builder,
    replay_poc,
    run_container,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from aixcc.db import (
    Bug,
    BugGroup,
    BugProfile,
    Patch,
    PatchBug,
    Task,
    TaskStatusEnum,
    make_session,
)
from aixcc.utils import search_available_patch_query
from patchagent.builder import OSSFuzzPoC
from patchagent.builder.utils import (
    BuilderProcessError,
    BuilderTimeoutError,
    DockerUnavailableError,
    safe_subprocess_run,
)

TESTING = False

already_built_edge = set()  # record edge: (patch_id, bug_profile_id)


def sync_already_built_edge() -> None:
    """
    Sync the already_built_edge set with database data to avoid redundant work.
    This populates the set with (patch_id, bug_profile_id) pairs that already have PatchBug entries.
    """
    global already_built_edge

    with make_session() as session:
        # Query all existing patch-bug combinations and group by (patch_id, bug_profile_id)
        existing_combinations = (
            session.query(PatchBug.patch_id, BugProfile.id.label("bug_profile_id"))
            .join(Bug, PatchBug.bug_id == Bug.id)
            .join(BugGroup, Bug.id == BugGroup.bug_id)
            .join(BugProfile, BugGroup.bug_profile_id == BugProfile.id)
            .distinct()
            .all()
        )

        for patch_id, bug_profile_id in existing_combinations:
            already_built_edge.add((patch_id, bug_profile_id))

    print(f"[🔄] Synced {len(already_built_edge)} already built edges from database")


def batch_level_reproduce(bug_list: List[Bug], patch: Patch, builder: ReproBuilder) -> bool:
    raw_patch = base64.b64decode(patch.patch).decode()
    if raw_patch == "":
        print(f"[🫠🫠🫠] Fail to reuse the patch {patch.id} due to empty patch")
        return False

    # currently, we're in the same bug_profile_id, so the harness name is the same.
    poc_list = [OSSFuzzPoC(Path(bug.poc), bug.harness_name) for bug in bug_list]
    pocs = copy_poc_to_builder(poc_list, builder)
    pocs = [poc for poc in pocs if poc is not None]
    if not pocs:
        print(f"[🫠🫠🫠] Fail to reuse the patch {patch.id} due to empty poc")
        return False

    harness_name = pocs[0].harness_name
    pocs_dir = pocs[0].path.parent  # all pocs are in the same directory
    sanitizer = SANITIZER_MAP.get(bug_list[0].sanitizer, bug_list[0].sanitizer)  # all bugs have the same sanitizer, we only consider it once
    fuzz_tooling_path = builder.fuzz_tooling_path  # Remeber fuzz_tooling is per task.
    builder_source_path = builder.source_path

    hash_key = f"{hashlib.md5(raw_patch.encode()).hexdigest()}-{sanitizer}"
    workspace = builder.workspace / hash_key  # for a task's builder, we dispatch build to different workspace based on the hash_key

    print(f"poc_dir: {pocs_dir} poc number: {len(pocs)}")
    build_finish_indicator = workspace / ".build"
    source_path_under_workspace = workspace / builder.org_source_path.name
    fuzz_tooling_path_under_workspace = workspace / builder.org_fuzz_tooling_path.name

    if build_finish_indicator.is_file():
        print(f"[🔍] Skip the build for {hash_key} because it has already been built")
    else:
        print(f"[🧱] Building {builder.project} with patch {hash_key}")

        shutil.rmtree(workspace, ignore_errors=True)
        shutil.copytree(builder_source_path, source_path_under_workspace, symlinks=True)
        shutil.copytree(fuzz_tooling_path, fuzz_tooling_path_under_workspace, symlinks=True)

        try:
            safe_subprocess_run(["patch", "-p1"], source_path_under_workspace, input=raw_patch.encode())
            builder._build_image(fuzz_tooling_path_under_workspace)
            print(f"[🧱] Build {builder.project} with patch {hash_key} finished")
            safe_subprocess_run(
                [
                    "infra/helper.py",
                    "build_fuzzers",
                    "--sanitizer",
                    sanitizer,
                    "--clean",
                    builder.project,
                    source_path_under_workspace,
                ],
                fuzz_tooling_path_under_workspace,
            )
            print(f"[🧱] Build fuzzers {builder.project} with patch {hash_key} finished")
            build_finish_indicator.write_text(raw_patch)
        except (DockerUnavailableError, BuilderProcessError, BuilderTimeoutError) as e:
            print(f"[{e.__class__.__name__}] Failed to build patch: {e}")
            return False

    assert build_finish_indicator.is_file(), "Build failed"

    print(f"[{datetime.now()}] [🔄] (ReproBuilder) Replaying {builder.project}/{harness_name} and patch {hash_key}")

    run_container(fuzz_tooling_path_under_workspace.as_posix(), builder.project, pocs_dir, hash_key)

    _, returncode = replay_poc(fuzz_tooling_path_under_workspace.as_posix(), builder.project, harness_name, pocs_dir, hash_key)

    repaired_status = returncode == 0  # True if reproduced (returncode is 0), False otherwise

    if not repaired_status:
        print(f"[🫠🫠🫠] Failed to reproduce {builder.project}/{harness_name} with patch {hash_key} returncode: {returncode}")
    else:
        print(f"[✅✅✅] Reproduced {builder.project}/{harness_name} with patch {hash_key} returncode: {returncode}")

    with make_session() as session:
        for bug in bug_list:
            if session.query(PatchBug).filter_by(patch_id=patch.id, bug_id=bug.id).count() == 0:
                patch_bug = PatchBug(patch_id=patch.id, bug_id=bug.id, repaired=repaired_status)
                print(f"time: {datetime.now()}, patch_id: {patch.id}, bug_id: {bug.id} -> {repaired_status}")
                try:
                    session.add(patch_bug)
                    session.commit()
                except IntegrityError:
                    session.rollback()

    return True


def reproduce_all_patches() -> None:
    # Sync with database at the start
    task_ids = []

    with make_session() as session:
        # Get task IDs and filter by status in the same query
        task_ids = session.scalars(select(Task.id).filter(Task.status.in_([TaskStatusEnum.processing, TaskStatusEnum.waiting])).order_by(func.random())).all()
        print(f"task_ids: {task_ids}")

    for task_id in task_ids:
        builder: ReproBuilder = create_builder(task_id)

        with make_session() as session:
            bug_profile_ids = session.scalars(select(BugProfile.id).filter(BugProfile.task_id == task_id).order_by(func.random())).all()

            valid_combinations = []
            for bug_profile_id in bug_profile_ids:
                # No need for task status check anymore - already filtered above
                patches = search_available_patch_query(session, bug_profile_id).all()
                other_bug_profile_ids = [id for id in bug_profile_ids if id != bug_profile_id]

                for patch, other_bug_profile_id in product(patches, other_bug_profile_ids):
                    valid_combinations.append((bug_profile_id, patch, other_bug_profile_id))

            sync_already_built_edge()

            valid_combinations.sort(key=lambda x: (x[1].id, x[2]) in already_built_edge)

            # print(f"valid_combinations: \n{valid_combinations}")
            for bug_profile_id, patch, other_bug_profile_id in valid_combinations:
                bugs: List[Bug] = (
                    session.query(Bug)
                    .join(BugGroup)
                    .join(BugProfile)
                    .outerjoin(PatchBug, (PatchBug.bug_id == Bug.id) & (PatchBug.patch_id == patch.id))
                    .filter(BugProfile.task_id == task_id, BugGroup.bug_profile_id == other_bug_profile_id, PatchBug.id.is_(None))
                    .order_by(func.random())
                    .limit(1000)
                    .all()
                )

                if not bugs:
                    continue

                print(
                    f"time: {datetime.now()}, [🔍] task_id {task_id} patch profile_id {bug_profile_id} patch_id {patch.id} repro bug_profile_id {other_bug_profile_id} bug number {len(bugs)}"
                )
                updated = batch_level_reproduce(bugs, patch, builder)
                if updated:
                    already_built_edge.add((patch.id, other_bug_profile_id))

            session.commit()


if __name__ == "__main__":
    while True:
        reproduce_all_patches()
        time.sleep(20)
