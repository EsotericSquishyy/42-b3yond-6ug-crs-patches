import time
from typing import Dict, List, Set, Tuple

from sqlalchemy import exists
from sqlalchemy.orm import Session

from aixcc.db import (
    BugProfile,
    BugProfileStatus,
    Patch,
    PatchBug,
    PatchStatus,
    PatchSubmit,
    PatchSubmitTimestamp,
    SubmissionStatusEnum,
    Task,
    TaskStatusEnum,
    make_session,
)
from aixcc.utils import search_available_patch_query


def get_available_bug_profiles_and_patches(session: Session, task_id: str) -> Tuple[List[BugProfile], List[Patch]]:
    """
    Returns a list of available bug profiles and patches for a given task.

    A bug profile is considered available if:
    1. It has no failed submissions
    2. It has fewer than 3 VALID patches already submitted, a patch is valid if
        a. It is not in PatchStatus or
        b. It is in PatchStatus and PatchStatus.functionality_tests_passing is not False

    A patch is considered available if it is associated with the bug profile and has no failing functionality tests.

    Args:
        session: Database session
        task_id: ID of the task to get bug profiles and patches for

    Returns:
        Tuple of (available_bug_profiles, available_patches)
    """

    # Get available bug profiles using subqueries to count valid patches
    all_bug_profiles: List[BugProfile] = (
        session.query(BugProfile)
        .filter(
            BugProfile.task_id == task_id,
            # No failed submissions
            ~exists().where(
                BugProfileStatus.bug_profile_id == BugProfile.id,
                BugProfileStatus.status == SubmissionStatusEnum.failed,
            ),
        )
        .all()
    )

    available_bug_profiles = []

    # Loop through all bug profiles to find the available ones
    for bug_profile in all_bug_profiles:
        # Count valid patches for this bug profile
        # A patch is valid if:
        # - It has no PatchStatus record, OR
        # - It has a PatchStatus record where functionality_tests_passing is not False

        # Get all patches for this bug profile
        all_patches = session.query(Patch).filter(Patch.bug_profile_id == bug_profile.id).all()

        valid_patch_count = 0
        for patch in all_patches:
            # Check if patch has a PatchStatus record
            patch_status = session.query(PatchStatus).filter(PatchStatus.patch_id == patch.id).first()

            # Patch is valid if no status or functionality_tests_passing is not False
            if patch_status is None or patch_status.functionality_tests_passing != False:
                valid_patch_count += 1

        # Bug profile is available if it has fewer than 3 valid patches
        if valid_patch_count < 3:
            available_bug_profiles.append(bug_profile)
            print(f"Bug profile {bug_profile.id} is available (has {valid_patch_count} valid patches)")

    # Collect all available patches from the available bug profiles
    available_patches: List[Patch] = []
    for bug_profile in available_bug_profiles:
        for patch in search_available_patch_query(session, bug_profile.id).all():
            available_patches.append(patch)

    return available_bug_profiles, available_patches


def build_cover_maps(session: Session, available_bug_profiles: List[BugProfile], available_patches: List[Patch]) -> Dict[int, Set[int]]:
    """
    Builds a cover map where each patch ID maps to a set of bug profile IDs it covers.

    A patch "covers" a bug profile if it fixes ALL bugs associated with that bug profile.

    Args:
        session: Database session
        available_bug_profiles: List of bug profiles to check
        available_patches: List of patches to analyze

    Returns:
        Dictionary mapping patch_id -> set of bug_profile_ids it fully covers
    """
    cover_map: Dict[int, Set[int]] = {patch.id: set() for patch in available_patches}

    for bug_profile in available_bug_profiles:
        # Get all bug IDs associated with this bug profile
        bug_ids = [bg.bug_id for bg in bug_profile.bug_groups]
        total_bugs: int = len(bug_ids)

        # Skip if bug profile has no associated bugs
        if total_bugs == 0:
            continue

        for patch in available_patches:
            unfixed_bugs: int = (
                session.query(PatchBug)
                .filter(
                    PatchBug.patch_id == patch.id,
                    PatchBug.bug_id.in_(bug_ids),
                    PatchBug.repaired == False,
                )
                .count()  # Use count() instead of len(all()) for efficiency
            )

            if unfixed_bugs > 0:
                continue

            # Count how many bugs from this profile are fixed by this patch
            fixed_bugs: int = (
                session.query(PatchBug)
                .filter(
                    PatchBug.patch_id == patch.id,
                    PatchBug.bug_id.in_(bug_ids),
                    PatchBug.repaired == True,
                )
                .count()  # Use count() instead of len(all()) for efficiency
            )

            if patch.bug_profile_id == bug_profile.id:
                cover_map[patch.id].add(bug_profile.id)
            elif fixed_bugs == total_bugs or fixed_bugs >= 1000:
                cover_map[patch.id].add(bug_profile.id)

    return cover_map


def select_patch(task: Task) -> None:
    """
    Selects optimal patches for submission for a given task.

    The algorithm:
    1. Gets all available bug profiles and patches
    2. Builds a coverage map showing which patches fix which bug profiles
    3. Filters out "dominated" patches (patches whose coverage is a proper subset of another patch)
    4. Avoids re-submitting already submitted patches
    5. Only submits patches that cover new bug profiles not already covered

    Args:
        task: The task to select patches for
    """

    with make_session() as session:
        # Get available bug profiles and patches
        available_bug_profiles, available_patches = get_available_bug_profiles_and_patches(session, task.id)

        # Build coverage map: patch_id -> set of bug_profile_ids it covers
        cover_map: Dict[int, Set[int]] = build_cover_maps(session, available_bug_profiles, available_patches)

        # Find dominated patches (patches that are proper subsets of other patches)
        # These are considered "invalid" because there's a better patch that covers more
        invalid_patch: Set[int] = set()
        for patch_id_1 in cover_map:
            for patch_id_2 in cover_map:
                # Skip comparing a patch with itself
                if patch_id_1 == patch_id_2:
                    continue

                # If patch_1 covers a proper subset of what patch_2 covers, mark it as invalid
                if cover_map[patch_id_1].issubset(cover_map[patch_id_2]) and len(cover_map[patch_id_1]) < len(cover_map[patch_id_2]):
                    invalid_patch.add(patch_id_1)

        # Get valid patches (non-dominated patches)
        valid_patch: Set[int] = set(cover_map.keys()) - invalid_patch

        # Track which bug profiles are already covered by submitted patches
        covered_bug_profiles: Set[int] = set()
        already_submitted_patches: Set[int] = set()

        # Check which valid patches have already been submitted
        for patch_submit in session.query(PatchSubmit).filter(PatchSubmit.patch_id.in_(valid_patch)).all():
            covered_bug_profiles.update(cover_map.get(patch_submit.patch_id, set()))
            already_submitted_patches.add(patch_submit.patch_id)

        # Remove already submitted patches from valid patches
        valid_patch -= already_submitted_patches

        # Submit new patches that cover at least one uncovered bug profile
        for patch_id in valid_patch:
            # Get bug profiles this patch would cover
            patch_coverage = cover_map.get(patch_id, set())

            # Calculate new bug profiles this patch would cover
            new_coverage = patch_coverage - covered_bug_profiles

            # Only submit if this patch covers at least one new bug profile
            if new_coverage:
                covered_bug_profiles.update(patch_coverage)
                session.add(PatchSubmit(patch_id=patch_id))
                print(f"Submitting patch {patch_id} which covers {len(new_coverage)} new bug profiles")

        session.commit()


def process_tasks() -> None:
    """
    Process all active tasks once.
    """
    try:
        with make_session() as session:
            # Get all active tasks (processing or waiting)
            active_tasks = (
                session.query(Task)
                .filter(
                    Task.status.in_(
                        [
                            TaskStatusEnum.processing,
                            TaskStatusEnum.waiting,
                        ]
                    )
                )
                .all()
            )

            print(f"Found {len(active_tasks)} active tasks to process")

            # Process each task
            for task in active_tasks:
                # Get the last scan timestamp for this task
                last_scan = session.query(PatchSubmitTimestamp).filter(PatchSubmitTimestamp.task_id == task.id).order_by(PatchSubmitTimestamp.created_at.desc()).first()

                # Calculate if we need to scan again
                current_time_ms = int(time.time() * 1000)  # Current time in milliseconds

                # Calculate task total time in milliseconds
                task_created_at_ms = int(task.created_at.timestamp() * 1000)
                task_total_time_ms = task.deadline - task_created_at_ms

                # Calculate minimum scan interval: min(1 hour, task total time / 8)
                one_hour_ms = 60 * 60 * 1000  # 1 hour in milliseconds
                min_scan_interval_ms = min(one_hour_ms, task_total_time_ms // 8)

                should_scan = False
                if last_scan is None:
                    should_scan = True
                    print(f"Task {task.id}: No previous scan found, will process")
                else:
                    last_scan_time_ms = int(last_scan.created_at.timestamp() * 1000)
                    time_since_last_scan_ms = current_time_ms - last_scan_time_ms

                    should_scan = time_since_last_scan_ms > min_scan_interval_ms

                if should_scan:
                    print(f"Processing task {task.id} (project: {task.project_name})")
                    select_patch(task)

                    # Record the scan timestamp
                    scan_timestamp = PatchSubmitTimestamp(task_id=task.id)
                    session.add(scan_timestamp)
                    session.commit()

    except Exception as e:
        print(f"Fatal error in patch submitter: {e}")
        raise


def main() -> None:
    """
    Main entry point for the patch submitter.

    Runs the patch submission process every 1 minutes continuously.
    """
    print("Starting patch submitter - will run every 20 minutes")

    while True:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting patch submission cycle")
        process_tasks()
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Patch submission cycle completed")

        print("Waiting 1 minutes before next cycle...")
        time.sleep(60)


if __name__ == "__main__":
    main()
