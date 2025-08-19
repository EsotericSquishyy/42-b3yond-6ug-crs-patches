import asyncio
import os
import logging
import stat
import subprocess
import yaml

async def run_command(cmd, cwd = None, can_error = False, timeout = False) -> bytes:
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=False,
        )
        if timeout:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60
            )
        else:
            stdout, stderr = await process.communicate()
    except asyncio.TimeoutError:
        logging.error(f"Command timed out: {cmd}")
        process.kill()
        logging.error(f"Killed process: {cmd}")
        # await process.wait()
        logging.error(f"Process killed: {cmd}")
        return b"Timeout", b"Timeout"

    if can_error:
        return stdout, stderr
    else:
        if process.returncode != 0:
            print(stderr)
            raise RuntimeError(f"Command failed")

        return stdout, stderr

def is_elf(filepath):
    """Returns True if |filepath| is an ELF file."""
    result = subprocess.run(
        ["file", filepath], stdout=subprocess.PIPE, check=False)
    return b"ELF" in result.stdout
    
def is_shell_script(filepath):
    """Returns True if |filepath| is a shell script."""
    result = subprocess.run(
        ["file", filepath], stdout=subprocess.PIPE, check=False)
    return b"shell script" in result.stdout

def find_fuzz_targets(directory):
    """Returns paths to fuzz targets in |directory|."""
    fuzz_targets = []
    for filename in os.listdir(directory):
        path = os.path.join(directory, filename)
        if filename == "llvm-symbolizer":
            continue
        if filename.startswith("afl-"):
            continue
        if filename.startswith("jazzer_"):
            continue
        if not os.path.isfile(path):
            continue
        EXECUTABLE = stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
        if not os.stat(path).st_mode & EXECUTABLE:
            continue
        # Fuzz targets can either be ELF binaries or shell scripts (e.g. wrapper
        # scripts for Python and JVM targets or rules_fuzzing builds with runfiles
        # trees).
        if not is_elf(path) and not is_shell_script(path):
            continue
        # TODO: this env should not be here
        # if os.getenv("FUZZING_ENGINE") not in {"none", "wycheproof"}:
        with open(path, "rb") as file_handle:
            binary_contents = file_handle.read()
            if b"LLVMFuzzerTestOneInput" not in binary_contents:
                continue
        fuzz_targets.append(filename)
    return fuzz_targets

def is_jvm_project(oss_fuzz_path, project_name):
    """Returns True if |project_name| is a JVM project."""
    project_path = os.path.join(oss_fuzz_path, "projects", project_name)
    if not os.path.exists(project_path):
        logging.error(f"Project {project_name} not found at {project_path}")
        return False

    yaml_path = os.path.join(project_path, "project.yaml")
    if not os.path.exists(yaml_path):
        logging.error(f"project.yaml not found at {yaml_path}")
        return False

    try:
        with open(yaml_path, "r") as f:
            project_yaml = yaml.safe_load(f)
            language = project_yaml.get("language", "")
            return language.lower() == "jvm" or language.lower() == "java" 
    except Exception as e:
        logging.error(f"Error reading project.yaml: {e}")
        return False

    return False

class OSSFuzzRunner:
    def __init__(self, fuzzing_tooling, project_name, src_path, workspace_dir = None):
        self.fuzzing_tooling = fuzzing_tooling
        self.fuzz_helper = os.path.join(fuzzing_tooling, 'infra/helper.py')
        self.project_name = project_name
        self.src_path = src_path
        self.workspace_dir = workspace_dir

    async def _build_fuzzers(self, is_pull = False):
        logging.info('Building images for %s', self.project_name)
        if is_pull:
            await run_command([
                'python3',
                self.fuzz_helper,
                'build_image',
                '--pull',
                self.project_name,
            ], 
            cwd=self.workspace_dir)
        else:
            await run_command([
                'python3',
                self.fuzz_helper,
                'build_image',
                '--no-pull',
                self.project_name,
            ], 
            cwd=self.workspace_dir)
        # TODO: detect sanitizers
        logging.info('Building fuzzers for %s', self.project_name)
        await run_command([
            'python3',
            self.fuzz_helper,
            'build_fuzzers',
            '--clean',
            self.project_name,
            self.src_path,
        ],
        cwd=self.workspace_dir)
        logging.info('Checking the building for %s', self.project_name)
        await run_command([
            'python3',
            self.fuzz_helper,
            'check_build',
            self.project_name,
        ],
        cwd=self.workspace_dir)
        logging.info('Searching for fuzz targets for %s', self.project_name)
        out_dir = os.path.join(self.fuzzing_tooling, 'build/out', self.project_name)
        self.fuzz_targets = find_fuzz_targets(out_dir)
        logging.info('Fuzz targets found: %s', self.fuzz_targets)
        return self.fuzz_targets
    
    def build_fuzzers(self, is_pull = False):
        return asyncio.run(self._build_fuzzers(is_pull))
    
    async def _reproduce(self, poc, harness):
        result = await run_command([
            'python3',
            self.fuzz_helper,
            'reproduce',
            self.project_name,
            harness,
            f'{poc}',
        ],
        can_error = True,
        timeout = True)
        return result

    def reproduce(self, poc, harness):
        return asyncio.run(self._reproduce(poc, harness))


    
    

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fuzzing_tooling = "/crs/tests/libpng/fuzz-tooling"
    project_name = "libpng"
    src_path = "/crs/tests/libpng/example-libpng"
    workspace_dir = "/crs/tests/libpng/workspace"
    runner = OSSFuzzRunner(fuzzing_tooling, project_name, src_path, workspace_dir)
    fuzz_targets = runner.build_fuzzers()
    print(fuzz_targets)
    harness = fuzz_targets[0]
    poc = "/crs/tests/libpng/poc"
    result = runner.reproduce(poc, harness)
    print(result)
