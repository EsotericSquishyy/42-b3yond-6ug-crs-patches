# Run SeedGen as a standalone pipeline on oss-fuzz project with local source repo
# Usage: python3 standalone.py <project_name> <path_to_fuzz_tooling> <path_to_src_dir> [--mini]

import os
import argparse

from utils.task import TaskData
from infra.aixcc import (
    validate_environment,
    load_project_config,
    print_project_info,
    run_mini_mode,
    run_mcp_mode,
    run_full_mode
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run SeedGen on an OSS-Fuzz project")
    parser.add_argument("project_name", type=str,
                        help="Name of the OSS-Fuzz project")
    parser.add_argument(
        "fuzz_tooling",
        type=str,
        help="Path to the fuzz tooling directory (oss-fuzz)",
    )
    parser.add_argument(
        "src_path",
        type=str,
        help="Path to the local project source directory",
    )
    parser.add_argument(
        "--mini",
        action="store_true",
        help="Run seedgen in mini mode",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run seedgen in MCP mode",
    )
    return parser.parse_args()


def build_and_run_targets(project_name, src_path, fuzz_tooling, mini=False, mcp_mode=False):
    os.makedirs(".tmp", exist_ok=True)

    project_yaml_path = validate_environment(fuzz_tooling, project_name)
    project_config = load_project_config(project_yaml_path)
    print_project_info(project_name, project_config)

    is_java = project_config["language"] in ["jvm", "java"]

    mock_task = TaskData(
        task_id="test-1234-5678",
        task_type="delta",
        project_name=project_name,
        focus="",
        repo=[],
        fuzz_tooling="",
        diff=""
    )

    if mcp_mode:
        run_mcp_mode(project_name, project_config,
                     src_path, fuzz_tooling, task=mock_task)
    elif is_java or mini:
        run_mini_mode(project_name, project_config,
                      src_path, fuzz_tooling, "gpt-4.1", task=mock_task)
    else:
        run_full_mode(project_name, project_config,
                      src_path, fuzz_tooling, task=mock_task)


def main():
    args = parse_args()
    project_name = args.project_name
    src_path = args.src_path
    fuzz_tooling = args.fuzz_tooling
    mini = args.mini
    mcp_mode = args.mcp

    build_and_run_targets(project_name, src_path, fuzz_tooling, mini, mcp_mode)


if __name__ == "__main__":
    main()
