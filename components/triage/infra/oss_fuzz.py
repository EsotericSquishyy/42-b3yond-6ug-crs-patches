import os
import yaml
import subprocess
import hashlib
import shutil
import uuid


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

        if project_config["language"] not in ["c", "c++"]:
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


def find_fuzzers(project_out_dir):
    """
    Looks for executables in the given directory 'LLVMFuzzerTestOneInput'.
    Returns a list of matching filenames.
    """

    fuzzers = []

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

    if not fuzzers:
        raise FileNotFoundError(
            "No executables found with the function 'LLVMFuzzerTestOneInput'")

    return fuzzers


def compile_project(fuzz_tooling, project_name, sanitizer, src_path):
    dockerfile_path = os.path.join(
        fuzz_tooling, "projects", project_name, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        raise FileNotFoundError("Dockerfile not found in project directory")
    if subprocess.run(["docker", "ps"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        raise FileNotFoundError("Docker not found on the host machine")

    if src_path:
        if not os.path.exists(os.path.abspath(src_path)):
            raise FileNotFoundError(
                f"Local source path {os.path.abspath(src_path)} doesn't exist")
        src_path = os.path.abspath(src_path)

    build_command = [
        f"{fuzz_tooling}/infra/helper.py",
        "build_image",
        "--no-pull",
        project_name,
    ]

    # print the command for debugging
    print(f"[+] Running command: {' '.join(build_command)}")

    subprocess.run(build_command, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    run_command = [
        f"{fuzz_tooling}/infra/helper.py",
        "build_fuzzers",
        "--clean",
    ]
    if sanitizer:
        run_command.append(f"--sanitizer={sanitizer}")
    run_command.extend([project_name, src_path])

    # print the command for debugging
    print(f"[+] Running command: {' '.join(run_command)}")

    subprocess.run(run_command, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_container(fuzz_tooling, project_name, poc_dir):
    image_name = 'base-runner'
    image_tag = ':v1.2.1'
    container_name = f'triage_runner_{hashlib.md5(fuzz_tooling.encode()).hexdigest()}'

    # Check if container already exists
    check_container_cmd = [
        'docker',
        'ps',
        '-a',
        '-q',
        '-f', f'name={container_name}'
    ]

    container_exists = subprocess.run(
        check_container_cmd, capture_output=True).stdout.decode().strip()

    if not container_exists:
        print(f"[+] Starting container {container_name}")
        run_base_runner_cmd = [
            'docker',
            'run',
            '-d',
            '--rm',
            '--name', container_name,
            '-v', f'{os.path.join(fuzz_tooling, "build", "out", project_name)}:/out',
            '-v', f'{poc_dir}:/poc',
            '-t',
            f'ghcr.io/aixcc-finals/{image_name}{image_tag}',
            'sleep', 'infinity'
        ]

        result = subprocess.run(run_base_runner_cmd, stdout=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to start runner container: {result.stdout.decode()}")
        print(f"[*] Started runner container {container_name}")
    else:
        print(f"[*] Using existing runner container {container_name}")


def cleanup_containers(name_prefix):
    result = subprocess.run(
        ['docker', 'ps', '--filter',
            f'name=^{name_prefix}', '--format', '{{.ID}}'],
        capture_output=True,
        text=True,
        check=True
    )
    container_ids = result.stdout.strip().splitlines()

    if container_ids:
        subprocess.run(['docker', 'stop'] + container_ids, check=True)


def replay_poc(fuzz_tooling, project_name, harness_binary, poc_path):
    poc_dir = os.path.abspath(os.path.join(".tmp", "poc"))
    os.makedirs(poc_dir, exist_ok=True)

    # Copy the POC file to the poc directory with the next available number
    poc_name = f"{uuid.uuid4()}"
    poc_dest = os.path.join(poc_dir, poc_name)
    shutil.copy2(poc_path, poc_dest)

    if os.getenv("TIMEOUT_OOM_TRIAGE", "none") == "processor":
        fuzzer_args = "-rss_limit_mb=2560 -timeout=50"
    else:
        fuzzer_args = "-rss_limit_mb=2560 -timeout=25"

    container_name = f'triage_runner_{hashlib.md5(fuzz_tooling.encode()).hexdigest()}'
    exec_reproduce_cmd = [
        'docker',
        'exec',
        '-w', '/usr/local/bin',
        '-e', f'TESTCASE=/poc/{poc_name}',
        '-e', f'FUZZER_ARGS={fuzzer_args}',
        container_name,
        'reproduce',
        harness_binary,
        '-runs=10'
    ]
    try:
        result = subprocess.run(
            exec_reproduce_cmd,
            capture_output=True,
            timeout=90
        )
        stdout = result.stdout.decode('utf-8', errors='ignore')
        stderr = result.stderr.decode('utf-8', errors='ignore')
        returncode = result.returncode
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode('utf-8', errors='ignore') if e.stdout else ''
        stderr = e.stderr.decode('utf-8', errors='ignore') if e.stderr else ''
        returncode = 1337

    os.remove(poc_dest)

    if "No such container" in stdout + stderr or returncode == 137:
        run_container(fuzz_tooling, project_name, poc_dir)
        raise RuntimeError(f"Runner container not found or killed: {stdout}")

    return stdout + stderr, returncode
