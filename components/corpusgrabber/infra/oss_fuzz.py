import os
import yaml
import subprocess


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


def print_project_info(project_name, project_config):
    # Describe the project with a fancy banner
    print("\n" + "=" * 50)
    print("Project Name: %s" % project_name)
    print("Homepage: %s" % project_config.get("homepage", "N/A"))
    print("Main Repo: %s" % project_config.get("main_repo", "N/A"))
    print("Language: %s" % project_config["language"])
    print("=" * 50 + "\n")


def find_fuzzers(project_name, fuzz_tooling_path):
    """
    Looks for executables in the given directory 'LLVMFuzzerTestOneInput'.
    Returns a list of matching filenames.
    """

    fuzzers = []

    project_out_dir = os.path.join(fuzz_tooling_path, "build", "out", project_name)
    project_dir = os.path.join(fuzz_tooling_path, "projects", project_name)

    project_yaml_path = validate_environment(fuzz_tooling_path, project_name)
    project_config = load_project_config(project_yaml_path)

    is_java = project_config["language"] in ["jvm", "java"]

    if is_java:
        # Java cases: look for "fuzzerTestOneInput" in src files under oss-fuzz/projects/...
        for root, _, files in os.walk(project_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                file_base, _ = os.path.splitext(filename)
                try:
                    with open(file_path, "r", errors="replace") as f:
                        content = f.read()
                except Exception:
                    # Skip files that cannot be read as text
                    continue

                if "fuzzerTestOneInput" in content:
                    fuzzers.append(file_base)
    else:
        # C cases: look for "LLVMFuzzerTestOneInput" in binaries under oss-fuzz/build/out/...
        for filename in os.listdir(project_out_dir):
            filepath = os.path.join(project_out_dir, filename)

            # We only care about regular files that are marked as executable
            if os.path.isfile(filepath) and os.access(filepath, os.X_OK):
                # Use 'strings' to check for the symbol name
                try:
                    result = subprocess.run(
                        ["strings", filepath],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                except subprocess.CalledProcessError:
                    # If 'strings' fails, skip this file
                    continue

                # Check if the symbol appears in the output
                if "LLVMFuzzerTestOneInput" in result.stdout:
                    fuzzers.append(filename) 

    # Read sanitizers from project config
    sanitizers = []
    if "sanitizers" in project_config:
        for sanitizer in project_config["sanitizers"]:
            sanitizers.append(sanitizer)
    
    # If no sanitizers specified in config, default to "none"
    if not sanitizers:
        sanitizers = ["none"]
    return fuzzers, sanitizers, is_java


def compile_project(fuzz_tooling, project_name, sanitizer, src_path):
    dockerfile_path = os.path.join(
        fuzz_tooling, "projects", project_name, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        raise FileNotFoundError("Dockerfile not found in project directory")
    if subprocess.run(["docker", "ps"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        raise FileNotFoundError("Docker not found on the host machine")
    
    if src_path:
        if not os.path.exists(os.path.abspath(src_path)):
            raise FileNotFoundError(f"Local source path {os.path.abspath(src_path)} doesn't exist")
        src_path = os.path.abspath(src_path)

    build_command = [
        f"{fuzz_tooling}/infra/helper.py",
        "build_image",
        "--no-pull",
        project_name,
    ]

    # print the command for debugging
    print(f"[+] Running command: {' '.join(build_command)}")

    subprocess.run(build_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    run_command = [
        f"{fuzz_tooling}/infra/helper.py",
        "build_fuzzers",
        "--clean",
    ]
    if sanitizer and sanitizer != 'jazzer':
        run_command.append(f"--sanitizer={sanitizer}")
    run_command.extend([project_name, src_path])


    # print the command for debugging
    print(f"[+] Running command: {' '.join(run_command)}")

    subprocess.run(run_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

