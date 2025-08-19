import os
import tarfile
import subprocess
import shutil

from dedup.codex_dedup import codex_dedup
from dedup.clusterfuzz_dedup import clusterfuzz_dedup

from utils.task import TaskData
import utils.db as db


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


def setup_repos(task: TaskData):
    work_dir = os.path.abspath(os.path.join(".tmp", task.task_id))
    os.makedirs(work_dir, exist_ok=True)

    # Extract repos
    extracted_repos = []
    for repo_path in task.repo:
        folder_name = extract_from_storage(repo_path, work_dir)
        extracted_repos.append(folder_name)

    # Extract fuzz_tooling
    fuzz_tooling_dir = extract_from_storage(
        task.fuzz_tooling, work_dir)

    # Extract diff
    diff_dir = extract_from_storage(task.diff, work_dir)

    # Apply the diff files
    if diff_dir:
        diff_path = os.path.join(work_dir, diff_dir)
        apply_diff_command = [
            "patch", "--batch", "--no-backup-if-mismatch", "-p1"]

        if os.path.isfile(diff_path) and (diff_path.endswith('.patch') or diff_path.endswith('.diff')):
            # diff_dir is a file, so apply it directly
            with open(diff_path, "rb") as patch_file:
                subprocess.run(apply_diff_command, stdin=patch_file, check=True, cwd=os.path.join(
                    work_dir, task.focus))
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
                            work_dir, task.focus))
                    print(
                        f"[+] Applied diff from {diff_file_path} to {task.focus}")
                else:
                    print(
                        f"[!] Diff file {diff_file_path} does not exist")
        else:
            print(
                f"[!] The provided diff path {diff_path} is neither a valid file nor a directory.")

    return work_dir


def do_dedup(
    task: TaskData,
    bug_profile_id: int,
    database_url: str,
    storage_dir: str,
    model: str
):
    """
    Perform deduplication for a bug profile against existing clusters.

    This function extracts repositories, retrieves crash information, and determines
    whether the current bug profile is a duplicate of an existing bug or represents
    a new unique bug. It either associates the profile with an existing cluster or
    creates a new cluster.

    Returns:
        tuple: (cluster_id, is_new_cluster) where:
            - cluster_id (int): ID of the cluster the bug profile was assigned to
            - is_new_cluster (bool): True if a new cluster was created, False if assigned to existing
            Returns (None, None) if deduplication couldn't be performed
    """
    work_dir = setup_repos(task)
    crash_new = db.query_for_crash(bug_profile_id, database_url)
    if not crash_new or crash_new == "N/A":
        return None, None

    # Get all existing clusters for this task
    existing_clusters = db.query_for_task_clusters(
        task.task_id, database_url)

    if not existing_clusters:
        # No clusters for this task yet, this is a new bug
        print(
            f"[*] First bug cluster for task {task.task_id}, adding new cluster")
        cluster_id = db.add_new_cluster_to_db(
            bug_profile_id, database_url)
        return cluster_id, True
    else:
        # Check each cluster for duplicates
        for cluster in existing_clusters:
            print(
                f"[*] Deduplicating in progress against bug cluster {cluster.id}")
            # Get all profiles in this cluster
            cluster_profiles = db.query_for_cluster_profiles(
                cluster.id, database_url)

            # Collect all valid crash reports from the cluster
            crash_bases = []
            for profile in cluster_profiles:
                if profile.summary and profile.summary != "N/A":
                    crash_bases.append(profile.summary)

            if not crash_bases:
                print(
                    f"[-] No valid crash reports found in cluster {cluster.id}, skipping")
                continue

            # Deduplicate against all crash reports in the cluster at once
            dedup_method = os.getenv("DEDUP_METHOD", None)

            if dedup_method == "codex":
                is_dupe = codex_dedup(
                    task.project_name, os.path.join(work_dir, task.focus),
                    crash_bases, crash_new, model,
                    os.path.join(storage_dir, "deduplicator",
                                 task.task_id, str(bug_profile_id))
                )
            elif dedup_method == "clusterfuzz":
                is_dupe = clusterfuzz_dedup(crash_bases, crash_new)
            else:
                is_dupe = False

            if is_dupe:
                print(
                    f"[*] Found a duplicate in cluster {cluster.id}")
                # Get any profile from this cluster to use for association
                if cluster_profiles:
                    cluster_id = db.associate_profile_to_cluster(
                        bug_profile_id, cluster_profiles[0], database_url)
                    return cluster_id, False
                break
        else:
            print(f"[*] No duplicate found, adding new cluster")
            cluster_id = db.add_new_cluster_to_db(
                bug_profile_id, database_url)
            return cluster_id, True
