import os
import shutil
import yaml
from opentelemetry import trace, context

from agent.filetype import get_filetype
from utils.telemetry import start_span_with_crs_inheritance

USERSPACE_CORPUS_DIR = "./corpus"

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

        if "language" not in project_config:
            raise ValueError("language not found in project.yaml")

        if project_config["language"] not in ["c", "c++", "java", "jvm"]:
            raise ValueError("Unsupported project language")

        return project_config


def find_files_with_fuzzer_function(src_path, oss_fuzz_project_dir, is_java):
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
    target_string = "fuzzerTestOneInput" if is_java else "LLVMFuzzerTestOneInput"

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

                if target_string in content:
                    result[file_base] = content

    return result


def copy_all_files_flat(src_dir, dest_dir):
    """
    Recursively copy all files from src_dir to dest_dir, flattening the structure.
    If two files share the same name, the latter will overwrite the former.
    """
    for root, _, files in os.walk(src_dir):
        for file in files:
            src_file = os.path.join(root, file)
            dest_file = os.path.join(dest_dir, file)
            try:
                shutil.copy2(src_file, dest_file)
            except Exception as e:
                print(f"Error copying {src_file} to {dest_file}: {e}")


def get_extensions_subdir_names():
    """
    Returns a list of all subdirectory names under the corpus/extensions directory.
    """
    extensions_dir = os.path.join(USERSPACE_CORPUS_DIR, "extensions")
    subdirs = []
    if os.path.isdir(extensions_dir):
        for entry in os.listdir(extensions_dir):
            full_path = os.path.join(extensions_dir, entry)
            if os.path.isdir(full_path):
                subdirs.append(entry)
    return subdirs


def grab_corpus(project_name, src_dir, fuzz_tooling_dir, task_dir):
    project_corpus = os.path.join(USERSPACE_CORPUS_DIR, "projects")
    filetype_corpus = os.path.join(USERSPACE_CORPUS_DIR, "extensions")

    project_dir = os.path.join(project_corpus, project_name)
    corpus_dest = os.path.join(task_dir, "corpus")
    os.makedirs(corpus_dest, exist_ok=True)

    if os.path.isdir(project_dir):
        # If we have handpicked corpus for a project, simply use it
        with start_span_with_crs_inheritance(
            f"grab project-based corpus"
        ):
            shutil.copytree(project_dir, corpus_dest, dirs_exist_ok=True)
        
    else:
        # Otherwise, use an agent to determine the filetypes
        # that the project expects, and grab them from filetype corpus
        with start_span_with_crs_inheritance(
            f"grab extension-based corpus"
        ) as span:
            project_yaml_path = validate_environment(fuzz_tooling_dir, project_name)
            project_config = load_project_config(project_yaml_path)

            is_java = project_config["language"] in ["jvm", "java"]

            oss_fuzz_project_dir = os.path.join(fuzz_tooling_dir, "projects", project_name)
            fuzzer_src_list = find_files_with_fuzzer_function(src_dir, oss_fuzz_project_dir, is_java)
            filetype_set = set()

            filetype_list = get_extensions_subdir_names()

            for fuzzer in fuzzer_src_list:
                filetype = get_filetype(fuzzer_src_list[fuzzer], project_name, filetype_list, task_dir)
                filetype = filetype.translate(str.maketrans('', '', "\"'`")).lower() # remove quotes and ticks
                filetype_set.add(filetype)
                print(f"[*] Found filetype for harness {fuzzer} to be `{filetype}`")

            filetype_set.discard("unknown")

            span.set_attribute("crs.action.target.filetypes", list(filetype_set))
            
            for filetype in filetype_set:
                ext_dir = os.path.join(filetype_corpus, filetype)
                if os.path.isdir(ext_dir):
                    copy_all_files_flat(ext_dir, corpus_dest)

    if not os.listdir(corpus_dest):
        return False
        
    return True