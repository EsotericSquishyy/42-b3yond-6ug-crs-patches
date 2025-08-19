import os
import shutil
from openai import BadRequestError
import subprocess
import yaml
from pathlib import Path

from agent.filetype import get_filetype


def oss_fuzz_projects(oss_fuzz_root):
    subprocess.run(
        ["git", "clone", "--depth", "1", "https://github.com/google/oss-fuzz", str(oss_fuzz_root)], 
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    projects = [project.name for project in (oss_fuzz_root / "projects").iterdir() if project.is_dir()]
    return projects


def validate_environment(root, project_name):
    if not os.path.exists(root):
        raise FileNotFoundError("OSS-Fuzz root directory not found")

    projects_dir = os.path.join(root, "projects")
    if not os.path.exists(projects_dir):
        raise FileNotFoundError("OSS-Fuzz projects directory not found")

    project_dir = os.path.join(projects_dir, project_name)
    if not os.path.exists(project_dir):
        raise FileNotFoundError(f"OSS-Fuzz project '{project_name}' not found")

    project_yaml_path = os.path.join(project_dir, "project.yaml")
    if not os.path.exists(project_yaml_path):
        raise FileNotFoundError("project.yaml not found in project directory")

    return project_yaml_path


def load_project_config(project_yaml_path):
    with open(project_yaml_path, "r") as f:
        project_config = yaml.safe_load(f)
        if not project_config:
            raise ValueError("project.yaml is empty or invalid")

        return project_config
    

def find_files_with_fuzzer_function(src_path, oss_fuzz_project_dir, project_config):
    """
    Iterates over all files under src_path and oss_fuzz_project_dir.
    For non-Java projects, it looks for the string "LLVMFuzzerTestOneInput".
    For Java projects, it looks for the string "fuzzerTestOneInput".
    
    Returns:
        dict: A dictionary where each key is a filename (without its extension) and
              the corresponding value is the file's content.
    """

    result = {}
    search_dirs = []

    # Validate and add directories if they exist
    if src_path and os.path.exists(src_path):
        search_dirs.append(src_path)
    if oss_fuzz_project_dir and os.path.exists(oss_fuzz_project_dir):
        search_dirs.append(oss_fuzz_project_dir)

    # Determine the target string based on project language
    if project_config["language"] in ["jvm", "java"]:
        target_strings = ["fuzzerTestOneInput"]
    elif project_config["language"] in ["go"]:
        target_strings = ["f.Fuzz", "F.Fuzz", "func Fuzz(data []byte)"]
    elif project_config["language"] in ["rust"]:
        target_strings = ["#[cfg(fuzzing)]", "#[cfg(any(test, fuzzing))]", "fuzz_logic", "fuzz_target"]
    elif project_config["language"] in ["python"]:
        target_strings = ["import atheris"]
    elif project_config["language"] in ["javascript"]:
        target_strings = ["module.exports.fuzz"]
    else:
        target_strings = ["LLVMFuzzerTestOneInput"] # works for C, C++, and Swift

    for directory in search_dirs:
        for root, _, files in os.walk(directory):
            for filename in files:
                file_path = os.path.join(root, filename)
                file_base, _ = os.path.splitext(filename)
                try:
                    with open(file_path, "r", errors="replace") as f:
                        content = f.read()
                except Exception:
                    # Skip files that cannot be read as text
                    continue
                
                for target_string in target_strings:
                    if target_string in content:
                        result[file_base] = content
                        break

    return result


def copy_seed_to_label(seed, label):
    label_dir = Path(__file__).resolve().parent / "extensions_llm" / label
    label_dir.mkdir(parents=True, exist_ok=True)

    dest_file = label_dir / seed.name
    try:
        shutil.copy2(seed, dest_file, follow_symlinks=False)
    except Exception as e:
        print(f"[!] Error copying {seed} to {dest_file}: {e}")


if __name__ == "__main__":
    oss_fuzz_dir = Path(__file__).resolve().parent / ".tmp" / "oss-fuzz"
    project_list = oss_fuzz_projects(oss_fuzz_dir)
    unknown_seed_dir = Path(__file__).resolve().parent / "extensions_magika" / "unknown"
    projects_file_types = {}
    projects_unknown_count = {}

    # Directory to clone the main repositories (using main_repo field) into.
    cloned_repos_dir = Path(__file__).resolve().parent / ".tmp" / "cloned_projects"
    cloned_repos_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = Path(__file__).resolve().parent / ".tmp" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Iterate over each subdirectory in the seed directory.
    for unknown_seed in unknown_seed_dir.iterdir():
        if unknown_seed.is_file():
            if unknown_seed.is_symlink():
                target = unknown_seed.resolve()
                # Use the parent directory's name of the symlink target as the project name.
                project_name = target.parent.name
                print(f"[*] Unknown seed {unknown_seed} belongs to project '{project_name}'.")
            else:
                continue

            if project_name in projects_file_types:
                # Project already processed before
                filetype_set = projects_file_types[project_name]
                print(f"[*] Project {project_name} already processed before, with filetype set of {filetype_set}")
            else:
                # Process project
                project_dir = oss_fuzz_dir / "projects" / project_name
                if project_dir.exists():
                    try:
                        # Validate the OSS-Fuzz environment for the project and read its project.yaml
                        project_yaml_path = validate_environment(str(oss_fuzz_dir), project_name)
                        project_config = load_project_config(project_yaml_path)
                    except Exception as e:
                        print(f"[!] Error loading config for project '{project_name}': {e}")
                        continue

                    # Read the 'main_repo' field from the configuration
                    main_repo_url = project_config.get("main_repo")
                    if not main_repo_url:
                        print(f"[!] Project '{project_name}' does not have a 'main_repo' field in its config.")
                        continue

                    # Define the destination path for cloning the project repository.
                    dest_repo_path = cloned_repos_dir / project_name
                    if dest_repo_path.exists():
                        print(f"[!] Repository for project '{project_name}' already exists at {dest_repo_path}, skipping clone.")
                        continue

                    print(f"[-] Cloning repository for project '{project_name}' from {main_repo_url} into {dest_repo_path}...")
                    try:
                        subprocess.run(
                            ["git", "clone", "--depth", "1", main_repo_url, str(dest_repo_path)],
                            check=True,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "false"}
                        )
                    except subprocess.CalledProcessError as e:
                        print(f"[!] Failed to clone repository for project '{project_name}': {e}")
                        continue

                    fuzzer_src_list = find_files_with_fuzzer_function(dest_repo_path, project_dir, project_config)
                    filetype_set = set()
                    projects_unknown_count[project_name] = 0

                    for fuzzer in fuzzer_src_list:
                        project_log_dir = logs_dir / project_name
                        project_log_dir.mkdir(parents=True, exist_ok=True)
                        try:
                            filetype = get_filetype(fuzzer_src_list[fuzzer], project_name, project_log_dir)
                            filetype = filetype.translate(str.maketrans('', '', "\"'`")).lower() # remove quotes and ticks
                            filetype_set.add(filetype)
                            print(f"[*] Found filetype for harness {fuzzer} to be `{filetype}`")
                            if filetype == "unknown":
                                projects_unknown_count[project_name] += 1
                        except BadRequestError:
                            continue
                        
                    filetype_set.discard("unknown")
                    projects_file_types[project_name] = filetype_set
                    shutil.rmtree(dest_repo_path)
                
                else:
                    print(f"[!] Project '{project_name}' not found in OSS-Fuzz directory.")
                    continue

            if len(filetype_set) == 0:
                print(f"[!] This project doesn't have any match, labelling seed as unknown")
                copy_seed_to_label(unknown_seed, "unknown")
                continue

            if projects_unknown_count[project_name] > 5:
                print(f"[!] This project matches with too many unknowns, labelling seed as unknown")
                copy_seed_to_label(unknown_seed, "unknown")
                continue

            if len(filetype_set) > 5:
                print(f"[!] This project matches with too many file types, labelling seed as unknown to reduce FPs")
                copy_seed_to_label(unknown_seed, "unknown")
                continue

            for filetype in filetype_set:
                copy_seed_to_label(unknown_seed, filetype)
            else:
                print(f"[*] Seed {unknown_seed} added to file types {filetype_set}")

                    
