#!/usr/bin/env python3

import os
import subprocess
import sys

# Path to the text file containing function_name, and path (without BITCODE_PATH prefix)
INPUT_FILE = os.path.join(os.getenv("SRC"), "/src/slice_target_functions.txt")

BITCODE_FOLDER ="42_aixcc_bitcode"

# Path to your local repository (where you'll run git commands, cmake, etc.)
PROJECT_PATH = os.path.join(os.getenv("SRC"), os.getenv("PROJECT_NAME"))
BITCODE_PATH = os.path.join(os.getenv("SRC"), os.getenv("PROJECT_NAME"), BITCODE_FOLDER)

# Exported compilers
STATIC_TOOLS_PATH = os.path.join(os.getenv("SRC"), "analyzer/build/lib/analyzer")

# Path to output
OUTPUT_DIR = os.getenv("OUT")

def main():
    # Use OUTPUT_DIR directly, since we already mounted according harness out directory in run_slice()
    harness_output_dir = OUTPUT_DIR
    
    # Change directory to the repo before we begin
    os.chdir(PROJECT_PATH)
    try:
        # 1. Collect complete function set
        function_set_file = os.path.join(harness_output_dir, "complete_function_set.txt")
        
        # First try BITCODE_PATH
        find_command = (
            f"find {BITCODE_PATH} -name '*.bc' "
            f"-exec llvm-nm --defined-only --no-demangle {{}} \\; | "
            f"grep -E ' [tT] ' | awk '{{print $3}}' > {function_set_file}"
        )
        result = subprocess.run(find_command, shell=True, capture_output=True)
        
        # If no .bc files found in BITCODE_PATH, try PROJECT_PATH
        if result.returncode != 0 or not os.path.getsize(function_set_file):
            find_command = (
                f"find {PROJECT_PATH} -name '*.bc' "
                f"-exec llvm-nm --defined-only --no-demangle {{}} \\; | "
                f"grep -E ' [tT] ' | awk '{{print $3}}' > {function_set_file}"
            )
            subprocess.run(find_command, shell=True, check=True)
            search_path = PROJECT_PATH
        else:
            search_path = BITCODE_PATH

        # Save bitcode files to harness_output_dir
        bitcode_output_dir = os.path.join(harness_output_dir, BITCODE_FOLDER)
        copy_command = f"mkdir -p {bitcode_output_dir} && cp -r {search_path}/* {bitcode_output_dir}/"
        print(f"Copying {search_path} to {bitcode_output_dir}")
        try:
            subprocess.run(copy_command, shell=True, check=True)
            print(f"Successfully copied {search_path} to {bitcode_output_dir}")
        except subprocess.CalledProcessError as e:
            print(f"Error copying {search_path} to {bitcode_output_dir}: {e}")
        
        # 2. Build the analyzer command:
        found_files_cmd = ["find", search_path, "-name", "*.bc"]
        found_files = subprocess.check_output(found_files_cmd).decode("utf-8").split()

        analyzer_cmd = [
            f"{STATIC_TOOLS_PATH}",
            f"--srcroot={PROJECT_PATH}",  # Update srcroot to use the correct path
            "--callgraph=true",
            "--slicing=true",
            f"--output={harness_output_dir}",
            f"--multi={INPUT_FILE}"
        ]
        analyzer_cmd.extend(found_files)

        # 3. Run the analyzer command
        subprocess.run(analyzer_cmd, check=True)

        # Print completion message
        print("Completed analysis using output directory")

    except subprocess.CalledProcessError as e:
        print(f"Error: {e}. Skipping...\n")

    finally:
        # Return to the repository root
        os.chdir(PROJECT_PATH)
        
if __name__ == "__main__":
    main()