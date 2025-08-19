# playground.py
# Run a basic container of the compiled project
# Usage: python3 playground.py <project_name>

import os
import subprocess
import argparse
import shutil
import itertools

import importlib.util
spec = importlib.util.spec_from_file_location("oss_fuzz", "./oss-fuzz.py")
oss_fuzz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oss_fuzz)


def parse_args():
    parser = argparse.ArgumentParser(description="Run a basic container of the compiled project")
    parser.add_argument("project_name", type=str, help="Name of the project")
    return parser.parse_args()

def run_project(project_name):
    artifacts_dir = os.path.abspath(os.path.join(".tmp", project_name))
    os.makedirs(artifacts_dir, exist_ok=True)

    # determine the runtime id. We get the largest number and plus one
    runtime_id = "playground"
    project_dir = os.path.join(artifacts_dir, str(runtime_id))

    # if project_dir exists, we need to clean it up
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)

    # copy files from .tmp/cache/<project_name> to .tmp/<project_name>/<runtime_id>
    shutil.copytree(os.path.join(".tmp", "cache", project_name), project_dir)
    if not os.path.exists(os.path.join(project_dir, "out")):
        raise FileNotFoundError(f"Project '{project_name}' not compiled")

    # create a "shared" folder in project_dir
    os.makedirs(os.path.join(project_dir, "shared"))

    docker_image_name = f"oss-fuzz-build-{project_name}"

    # Run the Docker container with the project image
    # Mount the `out` and `shared` directories to the temporary directory
    mount_configs = {
        "/out": f"{project_dir}/out",
        "/shared": f"{project_dir}/shared",
        "/getcov": oss_fuzz.get_prebuilt_binary_path("getcov"),
        "/seedd": oss_fuzz.get_prebuilt_binary_path("seedd"),
    }
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

    run_command = (
        [
            "docker",
            "run",
            "-it",
            "--privileged",
            "--shm-size=2g",
            "--entrypoint=/bin/bash",
            "--mount",
            f"type=volume,source={project_name}_src_cache,target=/src",
        ]
        + mount_commands
        + environment_commands
        + [docker_image_name]
    )
    # Run docker container interactively without capturing output
    # This allows user to interact with the container directly
    subprocess.run(run_command)


def main():
    args = parse_args()
    project_name = args.project_name

    project_yaml_path = oss_fuzz.validate_environment("oss-fuzz", project_name)
    project_config = oss_fuzz.load_project_config(project_yaml_path)
    oss_fuzz.compile_project("oss-fuzz", project_name, project_config)
    
    # run the project
    run_project(project_name)

if __name__ == "__main__":
    main()