import itertools
import os
import yaml
import subprocess
import shutil
import re
import stat
from concurrent.futures import ThreadPoolExecutor, as_completed
from opentelemetry import trace, context

from seedgen2.seedgen import SeedGenAgent
from seedgen2.seedmini import SeedMiniAgent
from seedgen2.seedcodex import SeedCodexAgent
from seedgen2.seedmcp import SeedMcpAgent

from utils.redis import get_redis_client
from utils.telemetry import start_span_with_crs_inheritance


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
    print("[+] Running SeedGen on OSS-Fuzz project: %s" % project_name)

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


def workdir_from_dockerfile(fuzz_tooling, project_name):
    WORKDIR_REGEX = re.compile(r'\s*WORKDIR\s*([^\s]+)')
    dockerfile_path = os.path.join(
        fuzz_tooling, "projects", project_name, "Dockerfile")
    with open(dockerfile_path) as file_handle:
        lines = file_handle.readlines()
    for line in reversed(lines):  # reversed to get last WORKDIR.
        match = re.match(WORKDIR_REGEX, line)
        if match:
            workdir = match.group(1)
            workdir = workdir.replace('$SRC', '/src')

            if not os.path.isabs(workdir):
                workdir = os.path.join('/src', workdir)

            return os.path.normpath(workdir)

    return os.path.join('/src', project_name)


# Compile the project, the artifacts will be stored in <fuzz_tooling>/build/out/<project_name>/
def compile_project(fuzz_tooling, project_name, project_config, src_path):
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

    # Copy tooling binaries to local project src directory
    tool_dir = os.path.join(src_path, "42_B3YOND_TOOLS")
    os.makedirs(tool_dir, exist_ok=True)
    tools = {
        os.path.join(tool_dir, "clang-argus"): get_prebuilt_binary_path("argus"),
        os.path.join(tool_dir, "clang-argus++"): get_prebuilt_binary_path("argus"),
        os.path.join(tool_dir, "bandld"): get_prebuilt_binary_path("bandld"),
        os.path.join(tool_dir, "libcallgraph_rt.a"): get_prebuilt_binary_path("libcallgraph_rt.a"),
        os.path.join(tool_dir, "SeedMindCFPass.so"): get_prebuilt_binary_path("SeedMindCFPass.so"),
    }
    for dest, src in tools.items():
        shutil.copyfile(src, dest)
        st = os.stat(dest)
        os.chmod(dest, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Setup the environment variables
    workdir = workdir_from_dockerfile(fuzz_tooling, project_name)
    environment_configs = {
        # Use Argus to compile the project
        "CC": f"{workdir}/42_B3YOND_TOOLS/clang-argus",
        "CXX": f"{workdir}/42_B3YOND_TOOLS/clang-argus++",
        # Argus settings (see https://github.com/whexy/argus for more details)
        "ADD_ADDITIONAL_PASSES": "SeedMindCFPass.so",
        "ADD_RUNTIME": "1",
        "BANDFUZZ_OPT": "0",
        "BANDFUZZ_PROFILE": "1",
        "BANDFUZZ_RUNTIME": "libcallgraph_rt.a",
        "GENERATE_COMPILATION_DATABASE": "1",
        "COMPILATION_DATABASE_DIR": "/out/compilation_database",
        # For OSS-Fuzz projects only:
        "FUZZING_LANGUAGE": project_config["language"],
        # For AIxCC CPs only:
        "CP_HARNESS_EXTRA_CFLAGS": "-fsanitize=fuzzer-no-link",
        "CP_HARNESS_EXTRA_CXXFLAGS": "-fsanitize=fuzzer-no-link",
        "CP_BASE_EXTRA_CFLAGS": "-fsanitize=fuzzer-no-link",
        "CP_BASE_EXTRA_CXXFLAGS": "-fsanitize=fuzzer-no-link",
        "CP_BASE_EXTRA_LDFLAGS": "-fsanitize=fuzzer-no-link",
    }
    environment_commands = list(
        itertools.chain.from_iterable(
            ("-e", f"{key}={value}") for key, value in environment_configs.items()
        )
    )

    run_command = (
        [
            f"{fuzz_tooling}/infra/helper.py",
            "build_fuzzers",
            "--clean",
            project_name,
            src_path,
        ]
        + environment_commands
    )

    # print the command for debugging
    print(f"[+] Running command: {' '.join(run_command)}")

    result = subprocess.run(run_command, capture_output=True,
                            universal_newlines=True, text=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            run_command,
            result.stdout + result.stderr
        )

    combined_output = result.stdout + result.stderr
    image_name = None
    # Look for "docker build -t "
    match = re.search(r'docker build.*?-t\s+(\S+)', combined_output, re.DOTALL)
    if match:
        image_name = match.group(1)
    else:
        # If not found, look for "=> => naming to "
        match = re.search(r"=> => naming to\s+(\S+)", combined_output)
        if match:
            image_name = match.group(1)

    if not image_name:
        raise ValueError(
            "Can't identify Docker image name from build_fuzzers command")

    return image_name, find_fuzzers(os.path.join(fuzz_tooling, "build/out", project_name))


# Run the project. All artifacts will be stored in .tmp/<project_name>
def run_project(project_dir, fuzz_tooling, image_name, project_name, src_path) -> tuple[str, str]:
    # Run the Docker container with the project image
    # Mount the `out` and `shared` directories to the temporary directory
    mount_configs = {
        "/out": f"{project_dir}/out",
        "/work": f"{project_dir}/work",
        "/shared": f"{project_dir}/shared",
        "/seedd": get_prebuilt_binary_path("seedd"),
        "/getcov": get_prebuilt_binary_path("getcov"),
    }
    if src_path:
        if not os.path.exists(os.path.abspath(src_path)):
            raise FileNotFoundError(
                f"Local source path {os.path.abspath(src_path)} doesn't exist")
        workdir = workdir_from_dockerfile(fuzz_tooling, project_name)
        mount_configs[f"{workdir}"] = os.path.abspath(src_path)
    mount_commands = list(
        itertools.chain.from_iterable(
            ("-v", f"{src}:{dest}") for dest, src in mount_configs.items()
        )
    )
    # Setup the environment variables
    environment_configs = {
        "ASAN_OPTIONS": "detect_leaks=0",
    }
    environment_commands = list(
        itertools.chain.from_iterable(
            ("-e", f"{key}={value}") for key, value in environment_configs.items()
        )
    )

    docker_command = [
        "docker",
        "run",
        "-d",
        "--privileged",
        "--shm-size=2g",
        "--entrypoint=/seedd",
    ]

    run_command = (
        docker_command
        + mount_commands
        + environment_commands
        + [image_name]
    )
    result = subprocess.run(run_command, check=True, capture_output=True)
    container_id = result.stdout.decode().strip()
    return container_id


def get_prebuilt_binary_path(binary_name):
    binary_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "prebuilt", binary_name
    )
    if not os.path.exists(binary_path):
        raise FileNotFoundError(
            f"{binary_name} not found. Please run `make clean` and then `make` in the root directory to build the tool.")
    return binary_path


def find_files_with_fuzzer_function(src_path, oss_fuzz_project_dir, is_java):
    """
    Iterates over all files under src_path and oss_fuzz_project_dir.
    For non-Java projects, it looks for the string "LLVMFuzzerTestOneInput".
    For Java projects, it looks for the string "fuzzerTestOneInput".

    Returns:
        dict: A dictionary where each key is a filename (without its extension) and
              the corresponding value is the file's content.
    """
    import os

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


def run_mini_mode(
    project_name,
    project_config,
    src_path,
    fuzz_tooling,
    gen_model,
    save_result_func=None,
    task=None,
    database_url="",
    storage_dir=""
):
    project_dir = os.path.abspath(os.path.join(
        ".tmp", "tasks", task.task_id, gen_model, "seedmini", project_name))
    os.makedirs(project_dir, exist_ok=True)

    oss_fuzz_project_dir = os.path.join(fuzz_tooling, "projects", project_name)
    is_java = project_config["language"] in ["jvm", "java"]

    fuzzers = find_files_with_fuzzer_function(
        src_path, oss_fuzz_project_dir, is_java)

    harness_binaries = list(fuzzers.keys())
    print(
        f"[*] Running SeedMini on all fuzzers: {harness_binaries} with Generative Model {gen_model}")

    def process_harness(harness_binary, parent_context):
        if harness_binary not in fuzzers:
            return

        token = context.attach(parent_context)
        try:
            with start_span_with_crs_inheritance(
                f"generate for harness {harness_binary}",
                attributes={"crs.action.target.harness": harness_binary}
            ):
                print(
                    f"[*] Running SeedMini for harness {harness_binary} with Generative Model {gen_model}")

                redis_client = get_redis_client()
                fuzzer_dir = os.path.join(project_dir, harness_binary)
                if os.path.exists(fuzzer_dir):
                    if redis_client:
                        is_done = redis_client.get(
                            f"seedmini:{task.task_id}:{gen_model}:{harness_binary}")
                        if is_done == b"done":
                            print(
                                f"[*] Harness {harness_binary} already processed. Skipping.")
                            return
                        else:
                            print(
                                f"[*] Incomplete fuzzer directory found for harness {harness_binary}, removing it.")
                            shutil.rmtree(fuzzer_dir)
                    else:
                        shutil.rmtree(fuzzer_dir)
                os.makedirs(fuzzer_dir, exist_ok=True)

                with start_span_with_crs_inheritance(
                    f"run seedmini agent"
                ):
                    agent = SeedMiniAgent(fuzzer_dir, project_name, harness_binary,
                                          fuzzers[harness_binary], gen_model)
                    agent.run()

                if save_result_func:
                    with start_span_with_crs_inheritance(
                        f"save to database"
                    ):
                        save_result_func(
                            database_url,
                            storage_dir,
                            task,
                            harness_binary,
                            os.path.join(fuzzer_dir, "seeds"),
                            "seedmini",
                            gen_model,
                            send_to_cmin=not is_java
                        )
                        print(
                            f"[*] SeedMini: Seeds stored in DB for task {task.task_id} for harness {harness_binary} with Generative Model {gen_model}")
                        # log_seedgen(task.task_id, "generated_seeds_mini", target=task.project_name,
                        #             harness_name=harness_binary, gen_model=gen_model)
                        redis_client = get_redis_client()
                        if redis_client:
                            redis_client.set(
                                f"seedmini:{task.task_id}:{gen_model}:{harness_binary}", "done")
        finally:
            context.detach(token)

    # Create a thread pool to parallelize the SeedMini execution per harness
    with ThreadPoolExecutor(max_workers=len(harness_binaries) or None) as executor:
        futures = [executor.submit(process_harness, hb, context.get_current())
                   for hb in harness_binaries]

        # Wait for all tasks to complete and handle any exceptions
        errors = {}
        for i, future in enumerate(as_completed(futures)):
            try:
                future.result()
            except Exception as exc:
                # Find which harness this future was processing
                for j, f in enumerate(futures):
                    if f == future:
                        harness_name = harness_binaries[j]
                        break
                else:
                    harness_name = f"unknown_harness_{i}"

                print(
                    f"[!] Harness '{harness_name}' failed with exception: {exc}")

                errors[harness_name] = exc

        if errors:
            error_details = "\n".join(
                [f"- {harness}: {error}" for harness, error in errors.items()])
            raise Exception(
                f"SeedMini failed for {len(errors)} harness(es):\n{error_details}")
        print(
            f"[*] SeedMini successfully executed on all harnesses with Generative Model {gen_model}")


def run_mcp_mode(
    project_name,
    project_config,
    src_path,
    fuzz_tooling,
    gen_model="llama3.1",
    save_result_func=None,
    save_to_triage_func=None,
    task=None,
    database_url="",
    storage_dir="",
    diff_dir=""
):
    project_dir = os.path.abspath(os.path.join(
        ".tmp", "tasks", task.task_id, gen_model, "seedmcp", project_name))
    os.makedirs(project_dir, exist_ok=True)

    oss_fuzz_project_dir = os.path.join(fuzz_tooling, "projects", project_name)
    is_java = project_config["language"] in ["jvm", "java"]

    fuzzers = find_files_with_fuzzer_function(
        src_path, oss_fuzz_project_dir, is_java)

    harness_binaries = list(fuzzers.keys())
    print(
        f"[*] Running SeedMCP on all fuzzers: {harness_binaries} with Generative Model {gen_model}")

    def process_harness(harness_binary, parent_context):
        if harness_binary not in fuzzers:
            return
        token = context.attach(parent_context)
        try:
            with start_span_with_crs_inheritance(
                f"generate for harness {harness_binary}",
                attributes={"crs.action.target.harness": harness_binary}
            ):
                print(
                    f"[*] Running SeedMCP for harness {harness_binary} with Generative Model {gen_model}")

                redis_client = get_redis_client()
                fuzzer_dir = os.path.join(project_dir, harness_binary)
                if os.path.exists(fuzzer_dir):
                    if redis_client:
                        is_done = redis_client.get(
                            f"seedmcp:{task.task_id}:{gen_model}:{harness_binary}")
                        if is_done == b"done":
                            print(
                                f"[*] Harness {harness_binary} already processed. Skipping.")
                            return
                        else:
                            print(
                                f"[*] Incomplete fuzzer directory found for harness {harness_binary}, removing it.")
                            shutil.rmtree(fuzzer_dir)
                    else:
                        shutil.rmtree(fuzzer_dir)
                os.makedirs(fuzzer_dir, exist_ok=True)

                with start_span_with_crs_inheritance(
                    f"run seedmcp agent"
                ):
                    agent = SeedMcpAgent(fuzzer_dir, src_path, project_name, harness_binary,
                                         fuzzers[harness_binary], gen_model, diff_dir)
                    agent.run()

                if save_result_func:
                    with start_span_with_crs_inheritance(
                        f"save to database"
                    ):
                        save_result_func(
                            database_url,
                            storage_dir,
                            task,
                            harness_binary,
                            os.path.join(fuzzer_dir, "seeds"),
                            "seedmcp",
                            gen_model
                        )
                        print(
                            f"[*] SeedMCP: Seeds stored in DB for task {task.task_id} for harness {harness_binary} with Generative Model {gen_model}")

                        if save_to_triage_func:
                            sanitizers = []
                            if "sanitizers" in project_config:
                                for sanitizer in project_config["sanitizers"]:
                                    sanitizers.append(sanitizer)

                            save_to_triage_func(
                                task,
                                os.path.join(fuzzer_dir, "seeds"),
                                sanitizers,
                                [harness_binary],
                                storage_dir,
                                database_url
                            )

                        redis_client = get_redis_client()
                        if redis_client:
                            redis_client.set(
                                f"seedmcp:{task.task_id}:{gen_model}:{harness_binary}", "done")
        finally:
            context.detach(token)

    # Create a thread pool to parallelize the SeedMini execution per harness
    with ThreadPoolExecutor(max_workers=len(harness_binaries) or None) as executor:
        futures = [executor.submit(process_harness, hb, context.get_current())
                   for hb in harness_binaries]

        # Wait for all tasks to complete and handle any exceptions
        errors = {}
        for i, future in enumerate(as_completed(futures)):
            try:
                future.result()
            except Exception as exc:
                # Find which harness this future was processing
                for j, f in enumerate(futures):
                    if f == future:
                        harness_name = harness_binaries[j]
                        break
                else:
                    harness_name = f"unknown_harness_{i}"

                print(
                    f"[!] Harness '{harness_name}' failed with exception: {exc}")
                errors[harness_name] = exc

        if errors:
            error_details = "\n".join(
                [f"- {harness}: {error}" for harness, error in errors.items()])
            raise Exception(
                f"SeedMCP failed for {len(errors)} harness(es):\n{error_details}")
        print(
            f"[*] SeedMCP successfully executed on all harnesses with Generative Model {gen_model}")


def run_full_mode(
    project_name,
    project_config,
    src_path,
    fuzz_tooling,
    gen_model,
    save_result_func=None,
    task=None,
    database_url="",
    storage_dir=""
):
    is_java = project_config["language"] in ["jvm", "java"]

    if is_java:
        # Don't run full seedgen on Java projects
        return

    with start_span_with_crs_inheritance(
        f"build project"
    ):
        print(f"[*] Building project for seedgen: {project_name}")
        try:
            image_name, fuzzers = compile_project(
                fuzz_tooling, project_name, project_config, src_path)
        except Exception as e:
            print(f"[!] Error occurred when building {project_name}:", e)
            raise

    project_dir = os.path.abspath(os.path.join(
        ".tmp", "tasks", task.task_id, gen_model, "seedgen", project_name))
    os.makedirs(project_dir, exist_ok=True)

    # copy files from <fuzz_tooling>/build/out/<project_name> to .tmp/<project_name>
    shutil.copytree(os.path.join(fuzz_tooling, "build/out", project_name),
                    os.path.join(project_dir, "out"), dirs_exist_ok=True)
    shutil.copytree(os.path.join(fuzz_tooling, "build/work", project_name),
                    os.path.join(project_dir, "work"), dirs_exist_ok=True)
    if not os.path.exists(os.path.join(project_dir, "out")):
        raise FileNotFoundError(f"Project '{project_name}' not compiled")

    # create a "shared" folder in project_dir
    os.makedirs(os.path.join(project_dir, "shared"), exist_ok=True)

    print(
        f"[*] Running seedgen on all fuzzers: {fuzzers} with Generative Model {gen_model}")
    harness_binaries = fuzzers

    def process_harness(harness_binary, parent_context):
        if harness_binary not in fuzzers:
            return
        token = context.attach(parent_context)
        try:
            with start_span_with_crs_inheritance(
                f"generate for harness {harness_binary}",
                attributes={"crs.action.target.harness": harness_binary}
            ):
                print(
                    f"[*] Running Seedgen for harness {harness_binary} with Generative Model {gen_model}")
                try:
                    # Start the daemon
                    container_id = run_project(
                        project_dir, fuzz_tooling, image_name, project_name, src_path)
                    redis_client = get_redis_client()
                    fuzzer_dir = os.path.join(project_dir, harness_binary)
                    if os.path.exists(fuzzer_dir):
                        if redis_client:
                            is_done = redis_client.get(
                                f"seedgen:{task.task_id}:{gen_model}:{harness_binary}")
                            if is_done == b"done":
                                print(
                                    f"[*] Harness {harness_binary} already processed. Skipping.")
                                return
                            else:
                                print(
                                    f"[*] Incomplete fuzzer directory found for harness {harness_binary}, removing it.")
                                shutil.rmtree(fuzzer_dir)
                        else:
                            shutil.rmtree(fuzzer_dir)
                    os.makedirs(fuzzer_dir, exist_ok=True)

                    shutil.copytree(os.path.join(project_dir, "out"), os.path.join(
                        fuzzer_dir, "out"), dirs_exist_ok=True)
                    shutil.copytree(os.path.join(project_dir, "work"), os.path.join(
                        fuzzer_dir, "work"), dirs_exist_ok=True)
                    # get ip address of the seedd container, the container id is container_id
                    with start_span_with_crs_inheritance(
                        f"run seedgen agent"
                    ):
                        ip_addr = subprocess.check_output(
                            ["docker", "inspect", "-f", "{{.NetworkSettings.IPAddress}}", container_id]).decode().strip()
                        agent = SeedGenAgent(fuzzer_dir, ip_addr,
                                             project_name, harness_binary, gen_model)
                        agent.run()
                except Exception as e:
                    print("Error occurred during full mode:", e)
                    raise
                finally:
                    if "container_id" in locals():
                        print(f"[-] Stopping container {container_id}")
                        subprocess.run(
                            ["docker", "stop", container_id], check=True)
                        subprocess.run(
                            ["docker", "rm", container_id], check=True)

                if save_result_func:
                    with start_span_with_crs_inheritance(
                        f"save to database"
                    ):
                        save_result_func(
                            database_url,
                            storage_dir,
                            task,
                            harness_binary,
                            os.path.join(fuzzer_dir, "seeds"),
                            "seedgen",
                            gen_model,
                            send_to_cmin=not is_java
                        )
                        print(
                            f"[*] Seedgen: Seeds stored in DB for task {task.task_id} for harness {harness_binary} with Generative Model {gen_model}")
                        redis_client = get_redis_client()
                        if redis_client:
                            redis_client.set(
                                f"seedgen:{task.task_id}:{gen_model}:{harness_binary}", "done")
        finally:
            context.detach(token)

    # Create a thread pool to parallelize the Seedgen execution per harness
    with ThreadPoolExecutor(max_workers=len(harness_binaries) or None) as executor:
        futures = [executor.submit(process_harness, hb, context.get_current())
                   for hb in harness_binaries]

        # Wait for all tasks to complete and handle any exceptions
        errors = {}
        for i, future in enumerate(as_completed(futures)):
            try:
                future.result()
            except Exception as exc:
                # Find which harness this future was processing
                for j, f in enumerate(futures):
                    if f == future:
                        harness_name = harness_binaries[j]
                        break
                else:
                    harness_name = f"unknown_harness_{i}"

                print(
                    f"[!] Harness '{harness_name}' failed with exception: {exc}")
                errors[harness_name] = exc

        if errors:
            error_details = "\n".join(
                [f"- {harness}: {error}" for harness, error in errors.items()])
            raise Exception(
                f"Seedgen Full mode failed for {len(errors)} harness(es):\n{error_details}")
        print(
            f"[*] Seedgen Full mode successfully executed on all harnesses with Generative Model {gen_model}")


def run_codex_mode(
    project_name,
    project_config,
    src_path,
    fuzz_tooling,
    gen_model,
    save_result_func=None,
    task=None,
    database_url="",
    storage_dir=""
):
    # Skip models that don't have Response API
    if "claude" in gen_model:
        return

    project_dir = os.path.abspath(os.path.join(
        ".tmp", "tasks", task.task_id, gen_model, "seedcodex", project_name))
    os.makedirs(project_dir, exist_ok=True)

    oss_fuzz_project_dir = os.path.join(fuzz_tooling, "projects", project_name)
    is_java = project_config["language"] in ["jvm", "java"]

    fuzzers = find_files_with_fuzzer_function(
        src_path, oss_fuzz_project_dir, is_java)

    harness_binaries = list(fuzzers.keys())
    print(
        f"[*] Running SeedCodex on all fuzzers: {harness_binaries} with Generative Model {gen_model}")

    def process_harness(harness_binary, parent_context):
        if harness_binary not in fuzzers:
            return

        token = context.attach(parent_context)
        try:
            with start_span_with_crs_inheritance(
                f"generate for harness {harness_binary}",
                attributes={"crs.action.target.harness": harness_binary}
            ):
                print(
                    f"[*] Running SeedCodex for harness {harness_binary} with Generative Model {gen_model}")

                redis_client = get_redis_client()
                fuzzer_dir = os.path.join(project_dir, harness_binary)
                if os.path.exists(fuzzer_dir):
                    if redis_client:
                        is_done = redis_client.get(
                            f"seedcodex:{task.task_id}:{gen_model}:{harness_binary}")
                        if is_done == b"done":
                            print(
                                f"[*] Harness {harness_binary} already processed. Skipping.")
                            return
                        else:
                            print(
                                f"[*] Incomplete fuzzer directory found for harness {harness_binary}, removing it.")
                            shutil.rmtree(fuzzer_dir)
                    else:
                        shutil.rmtree(fuzzer_dir)
                os.makedirs(fuzzer_dir, exist_ok=True)

                with start_span_with_crs_inheritance(
                    f"run seedcodex agent"
                ):
                    agent = SeedCodexAgent(fuzzer_dir, project_name, harness_binary,
                                           fuzzers[harness_binary], src_path,
                                           gen_model)
                    agent.run()

                if save_result_func:
                    with start_span_with_crs_inheritance(
                        f"save to database"
                    ):
                        save_result_func(
                            database_url,
                            storage_dir,
                            task,
                            harness_binary,
                            os.path.join(fuzzer_dir, "seeds"),
                            "seedcodex",
                            gen_model,
                            send_to_cmin=not is_java
                        )
                        print(
                            f"[*] SeedCodex: Seeds stored in DB for task {task.task_id} for harness {harness_binary} with Generative Model {gen_model}")
                        # log_seedgen(task.task_id, "generated_seeds_codex", target=task.project_name,
                        #             harness_name=harness_binary, gen_model=gen_model)
                        redis_client = get_redis_client()
                        if redis_client:
                            redis_client.set(
                                f"seedcodex:{task.task_id}:{gen_model}:{harness_binary}", "done")
        finally:
            context.detach(token)

    # Create a thread pool to parallelize the SeedMini execution per harness
    with ThreadPoolExecutor(max_workers=len(harness_binaries) or None) as executor:
        futures = [executor.submit(process_harness, hb, context.get_current())
                   for hb in harness_binaries]

        # Wait for all tasks to complete and handle any exceptions
        errors = {}
        for i, future in enumerate(as_completed(futures)):
            try:
                future.result()
            except Exception as exc:
                # Find which harness this future was processing
                for j, f in enumerate(futures):
                    if f == future:
                        harness_name = harness_binaries[j]
                        break
                else:
                    harness_name = f"unknown_harness_{i}"

                print(
                    f"[!] Harness '{harness_name}' failed with exception: {exc}")
                errors[harness_name] = exc

        if errors:
            error_details = "\n".join(
                [f"- {harness}: {error}" for harness, error in errors.items()])
            raise Exception(
                f"SeedCodex failed for {len(errors)} harness(es):\n{error_details}")
        print(
            f"[*] SeedCodex successfully executed on all harnesses with Generative Model {gen_model}")
