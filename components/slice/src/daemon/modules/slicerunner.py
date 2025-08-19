import os
import logging
import subprocess
from pathlib import Path

import docker
from daemon.modules.workspace import WorkspaceManager
from utils.docker_slice import _env_to_docker_args, docker_run
from daemon.modules.telemetry import log_telemetry_action, span_decorator

BITCODE_FOLDER ="42_aixcc_bitcode"

class SliceRunner:
    def __init__(self, project_name, workspace_manager: WorkspaceManager, slice_target, span, image_prefix='aixcc-afc'):
        """
        Initializes the SliceRunner with the given parameters.

        Args:
            project_name (str): The name of the project.
            workspace_manager (WorkspaceManager): An instance of WorkspaceManager.
            slice_target (list): List of (path, func) tuples for slice targets.
            image_prefix (str): Docker image prefix/registry (default: 'aixcc-afc')
        """
        self.project_name = project_name
        self.workspace_manager = workspace_manager
        self.slice_target = slice_target
        self.image_prefix = image_prefix
        self.effective_image_name = None  # Will store the actual image name used

        # Use the workspace provided by WorkspaceManager.
        self.workspace_dir = self.workspace_manager.workspace_dir

        # Retrieve the focused repository from the workspace.
        focused_repo = self.workspace_manager.get_focused_repo()
        if not focused_repo:
            raise ValueError("Focused repository not found in the workspace.")
        self.focused_repo = focused_repo  # Path object is fine, will auto-convert when needed

        # Set output directories relative to the workspace.
        self.slice_in = self.workspace_manager.fuzzing_tooling_path / "build" / "out" / self.project_name / BITCODE_FOLDER
        self.slice_out = self.workspace_dir / 'slice_out'
        self.slice_work = self.workspace_dir / 'slice_work'
        self.slice_out.mkdir(exist_ok=True)
        self.slice_work.mkdir(exist_ok=True)
        
        self.helper_path = self.workspace_manager.helper_path
        self.docker_client = docker.from_env()
        self.current_span = span

    @span_decorator("prepare")
    def prepare(self):
        """
        Prepare the environment by building the Docker image and fuzzers.
        Returns:
            bool: True if preparation is successful, False otherwise.
        """
        if not self._build_docker_image():
            logging.error(f"Failed to build Docker image for project '{self.project_name}'")
            return False
        if not self._build_fuzzers():
            logging.error(f"Failed to build fuzzers for project '{self.project_name}'")
            return False
        return True

    @span_decorator("build_docker_image")
    def _build_docker_image(self):
        """
        Checks if a standard or legacy Docker image exists. If not, attempts to build
        using the helper script and then re-checks which image (standard or legacy)
        was potentially created. Sets self.effective_image_name accordingly.
        Returns:
            bool: True if a usable image is found or built, False otherwise.
        """
        image_name = f'{self.image_prefix}/{self.project_name}'
        legacy_image_name = f'gcr.io/oss-fuzz/{self.project_name}'
        log_telemetry_action(title=f"Checking for existing Docker image for project '{self.project_name}'", msg_list=[], action_name="build_docker_image", status="OK", level="info")
        
        # 1. Check for existing standard image
        try:
            self.docker_client.images.get(image_name)
            logging.info("Using existing standard Docker image '%s'.", image_name)
            self.effective_image_name = image_name
            log_telemetry_action(title="Check for existing standard image", msg_list=[f"Using existing standard Docker image '{image_name}'."], action_name="build_docker_image", status="OK", level="verbose")
            return True
        except docker.errors.ImageNotFound:
            logging.debug("Standard Docker image '%s' not found.", image_name)
            log_telemetry_action(title="Check for existing standard image", msg_list=[f"Standard Docker image '{image_name}' not found."], action_name="build_docker_image", status="ERROR", level="debug")
        except Exception as e:
             logging.error("Error checking for standard image '%s': %s", image_name, e)
             # Potentially recoverable, continue to check legacy
             log_telemetry_action(title="Check for existing standard image", msg_list=[f"Error checking for standard image '{image_name}': {e}"], action_name="build_docker_image", status="ERROR", level="debug")
        # 2. Check for existing legacy image
        try:
            self.docker_client.images.get(legacy_image_name)
            logging.info("Using existing legacy Docker image '%s'.", legacy_image_name)
            self.effective_image_name = legacy_image_name
            log_telemetry_action(title="Check for existing legacy image", msg_list=[f"Using existing legacy Docker image '{legacy_image_name}'."], action_name="build_docker_image", status="OK", level="verbose")
            return True
        except docker.errors.ImageNotFound:
            logging.info("Neither standard nor legacy Docker image found. Attempting build.")
            log_telemetry_action(title="Check for existing legacy image", msg_list=[f"Neither standard nor legacy Docker image found. Attempting build."], action_name="build_docker_image", status="ERROR", level="debug")
        except Exception as e:
             logging.error("Error checking for legacy image '%s': %s", legacy_image_name, e)
             # If standard check also failed, we probably can't proceed
             if self.effective_image_name is None:
                 return False
             log_telemetry_action(title="Check for existing legacy image", msg_list=[f"Error checking for legacy image '{legacy_image_name}': {e}"], action_name="build_docker_image", status="ERROR", level="debug")
            
        # 3. Attempt to build if neither image exists
        build_success = False
        try:
            logging.info("Building image for project '%s' using helper script.", self.project_name)
            cmd = ['python3', self.helper_path, 'build_image', '--no-pull', self.project_name]
            log_telemetry_action(title=f"Building image for project '{self.project_name}' using helper script.", msg_list=cmd, action_name="build_docker_image", status="OK", level="verbose")
            # Run the build process
            result = subprocess.run(cmd, capture_output=True, text=True, check=False) # Don't check=True yet
            
            if result.returncode == 0:
                logging.info("Build command executed successfully (stdout: %s)", result.stdout)
                log_telemetry_action(title=f"Build command executed successfully (stdout: {result.stdout})", msg_list=cmd, action_name="build_docker_image", status="OK", level="verbose")
                build_success = True # Mark build command success
            else:
                logging.warning("Build command failed (return code %d). stderr: %s", result.returncode, result.stderr)
                log_telemetry_action(title=f"Build command failed (return code {result.returncode}). stderr: {result.stderr}", msg_list=cmd, action_name="build_docker_image", status="ERROR", level="debug")
                # Proceed to check if image exists anyway, maybe helper logs error but still works partially
        except Exception as e:
            logging.error("An exception occurred during the build process: %s", e)
            # Proceed to check images, maybe it worked before exception

        # 4. Re-check for images after build attempt
        try:
            self.docker_client.images.get(image_name)
            logging.info("Found standard Docker image '%s' after build attempt.", image_name)
            self.effective_image_name = image_name
            log_telemetry_action(title=f"Found standard Docker image '{image_name}' after build attempt.", msg_list=[], action_name="build_docker_image", status="OK", level="verbose")
            return True
        except docker.errors.ImageNotFound:
            logging.debug("Standard Docker image '%s' still not found after build attempt.", image_name)
        except Exception as e:
             logging.error("Error checking for standard image '%s' post-build: %s", image_name, e)


        try:
            self.docker_client.images.get(legacy_image_name)
            logging.info("Found legacy Docker image '%s' after build attempt.", legacy_image_name)
            self.effective_image_name = legacy_image_name
            log_telemetry_action(title=f"Found legacy Docker image '{legacy_image_name}' after build attempt.", msg_list=[], action_name="build_docker_image", status="OK", level="verbose")
            return True
        except docker.errors.ImageNotFound:
            logging.debug("Legacy Docker image '%s' still not found after build attempt.", legacy_image_name)
            log_telemetry_action(title=f"Legacy Docker image '{legacy_image_name}' still not found after build attempt.", msg_list=[], action_name="build_docker_image", status="ERROR", level="debug")
        except Exception as e:
            logging.error("Error checking for legacy image '%s' post-build: %s", legacy_image_name, e)
            log_telemetry_action(title=f"Error checking for legacy image '{legacy_image_name}' post-build: {e}", msg_list=[], action_name="build_docker_image", status="ERROR", level="debug")

        # 5. If neither image found after build attempt
        logging.error("Failed to find or build a usable Docker image ('%s' or '%s').", image_name, legacy_image_name)
        log_telemetry_action(title=f"Failed to find or build a usable Docker image ('{image_name}' or '{legacy_image_name}').", msg_list=[], action_name="build_docker_image", status="ERROR", level="debug")
        self.effective_image_name = None
        return False

    @span_decorator("build_fuzzers")
    def _build_fuzzers(self):
        """
        Builds fuzzers using the helper script.
        Returns:
            bool: True if fuzzers were built successfully, False otherwise.
        """
        logging.info("Building fuzzers for project '%s'", self.project_name)
        cmd = [
            'python3', self.helper_path, 'build_fuzzers', 
            '--clean', self.project_name, self.focused_repo
        ]
        log_telemetry_action(title=f"Building fuzzers for project '{self.project_name}'", msg_list=cmd, action_name="build_fuzzers", status="OK", level="info")
        logging.info(f"Build command: {cmd}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logging.error("Error building fuzzers: %s", result.stderr)
            log_telemetry_action(title=f"Error building fuzzers: {result.stderr}", msg_list=cmd, action_name="build_fuzzers", status="ERROR", level="debug")
            return False
        log_telemetry_action(title=f"Fuzzers built successfully for project '{self.project_name}'", msg_list=cmd, action_name="build_fuzzers", status="OK", level="verbose")
        return True

    @span_decorator("write_slice_target_file")
    def _write_slice_target_file(self):
        """
        Writes the slice target functions and their paths into a file.
        
        Returns:
            Path: The path to the written file, or None if writing failed.
        """
        slice_target_file = self.workspace_dir / 'slice_targets.txt'
        log_telemetry_action(title=f"Writing slice target functions file to '{slice_target_file}'", msg_list=[], action_name="write_slice_target_file", status="OK", level="info")
        try:
            with open(slice_target_file, 'w') as f:
                for path, func in self.slice_target:
                    f.write(f'{path} {func}\n')
            logging.info("Slice target functions file written to '%s'", slice_target_file)
            log_telemetry_action(title=f"Slice target functions file written to '{slice_target_file}'", msg_list=[], action_name="write_slice_target_file", status="OK", level="verbose")
            return slice_target_file
        except Exception as e:
            logging.error("Error writing slice target functions file: %s", e)
            log_telemetry_action(title=f"Error writing slice target functions file: {e}", msg_list=[], action_name="write_slice_target_file", status="ERROR", level="debug")
            return None

    @span_decorator("run_slice")
    def run_slice(self):
        """
        Runs the slice analysis using Docker for each detected harness.
        
        Returns:
            bool: True if at least one harness analysis succeeded, False if all failed.
        """
        slice_target_file = self._write_slice_target_file()
        if not slice_target_file:
            logging.error("Failed to create slice target functions file, aborting slice run.")
            log_telemetry_action(title=f"Failed to create slice target functions file, aborting slice run.", msg_list=[], action_name="run_slice", status="ERROR", level="debug")
            return False
        log_telemetry_action(title=f"Slice target functions file created successfully", msg_list=[], action_name="run_slice", status="OK", level="verbose")

        # Ensure an image name was determined by _build_docker_image
        if not self.effective_image_name:
            logging.error("No effective Docker image found or built. Cannot run slice.")
            log_telemetry_action(title=f"No effective Docker image found or built. Cannot run slice.", msg_list=[], action_name="run_slice", status="ERROR", level="debug")
            return False
        log_telemetry_action(title=f"Effective Docker image found or built", msg_list=[], action_name="run_slice", status="OK", level="verbose")

        # Prepare all harness directories
        harness_dirs = self.prepare_harnesses()
        if not harness_dirs:
            logging.error("No harnesses found or failed to prepare harness directories.")
            log_telemetry_action(title=f"No harnesses found or failed to prepare harness directories.", msg_list=[], action_name="run_slice", status="ERROR", level="debug")
            return False
        log_telemetry_action(title=f"Harness directories prepared successfully", msg_list=harness_dirs, action_name="run_slice", status="OK", level="verbose")
        
        success = False
        total_harnesses = len(harness_dirs)
        current_harness = 0
        for harness_name, harness_dir in harness_dirs.items():
            current_harness += 1
            logging.info(f"Running slice analysis for harness: {harness_name} ({current_harness}/{total_harnesses})")
            log_telemetry_action(title=f"Running slice analysis for harness: {harness_name} ({current_harness}/{total_harnesses})", msg_list=[], action_name="run_slice", status="OK", level="info")
            
            env = [f'PROJECT_NAME={self.project_name}']
            command = _env_to_docker_args(env)
            command += [
                '-v', f'{harness_dir}:/src/{self.project_name}/{BITCODE_FOLDER}',
                '-v', f'{self.slice_out}/{harness_name}:/out',
                '-v', f'{self.slice_work}/{harness_name}:/work',
                '-v', f'{slice_target_file}:/src/slice_target_functions.txt',
                '-v', f'/app/slice.py:/src/slice.py',
                self.effective_image_name, # Use the determined image name
                'python3', '/src/slice.py', harness_name
            ]
            # Use precise logging for which image is being used
            logging.info(f"Running slice analysis for harness '{harness_name}' using image '{self.effective_image_name}'")
            log_telemetry_action(title=f"Running slice analysis for harness '{harness_name}' using image '{self.effective_image_name}'", msg_list=command, action_name="run_slice", status="OK", level="verbose")
            
            # Create output directory for this harness
            harness_out_dir = self.slice_out / harness_name
            harness_out_dir.mkdir(parents=True, exist_ok=True)
            
            result = docker_run(command)
            if not result:
                logging.error(f"Slice analysis failed for harness '{harness_name}'")
                log_telemetry_action(title=f"Slice analysis failed for harness '{harness_name}'", msg_list=command, action_name="run_slice", status="ERROR", level="debug")
            else:
                logging.info(f"Slice analysis succeeded for harness '{harness_name}'. Check '{harness_out_dir}' for details.")
                log_telemetry_action(title=f"Slice analysis succeeded for harness '{harness_name}'. Check '{harness_out_dir}' for details.", msg_list=[], action_name="run_slice", status="OK", level="verbose")
                # Track success of at least one harness
                success = True
                
                # Process results for this harness
                if not self.handle_slice_results(harness_out_dir):
                    logging.error(f"Failed to handle slice results for harness '{harness_name}'")
                    log_telemetry_action(title=f"Failed to handle slice results for harness '{harness_name}'", msg_list=[], action_name="run_slice", status="ERROR", level="debug")
        # Merge results from all harnesses
        if success:
            if not self.merge_slice_results():
                logging.error("Failed to merge slice results from all harnesses")
                log_telemetry_action(title=f"Failed to merge slice results from all harnesses", msg_list=[], action_name="run_slice", status="ERROR", level="debug")
                return False
            log_telemetry_action(title=f"Slice results merged successfully from all harnesses", msg_list=[], action_name="run_slice", status="OK", level="verbose")
        return success

    @span_decorator("handle_slice_results")
    def handle_slice_results(self, output_dir):
        """
        Processes the slicing output for a specific harness:
          - Computes the union of all lines from files ending with '.slicing_func_result'
            and writes them into 'result_directed'.
          - Computes the intersection of all lines from files ending with '.slicing_func_result_verbose'
            and writes them into 'result_sarif'.

        Args:
            output_dir (Path): The directory containing the slice output for a specific harness

        Returns:
            bool: True if processing is successful, False otherwise.
        """
        log_telemetry_action(title=f"Processing slice results for harness '{output_dir}'", msg_list=[], action_name="handle_slice_results", status="OK", level="info")
        # Process non-verbose results for result_directed.
        directed_files = list(output_dir.glob('*.slicing_func_result'))
        if not directed_files:
            logging.error(f"No '.slicing_func_result' files found in {output_dir}")
            log_telemetry_action(title=f"No '.slicing_func_result' files found in {output_dir}", msg_list=[], action_name="handle_slice_results", status="ERROR", level="debug")
            return False
        log_telemetry_action(title=f"'.slicing_func_result' files found in {output_dir}", msg_list=[], action_name="handle_slice_results", status="OK", level="verbose")
        union_set = set()
        for result_file in directed_files:
            try:
                with open(result_file, 'r') as f:
                    file_entries = {line.strip() for line in f if line.strip()}
                logging.debug("Read %d entries from '%s'.", len(file_entries), result_file.name)
                log_telemetry_action(title=f"Read {len(file_entries)} entries from '{result_file.name}'.", msg_list=[], action_name="handle_slice_results", status="OK", level="verbose")
                union_set |= file_entries
            except Exception as e:
                logging.error("Error reading file %s: %s", result_file, e)
                return False

        # Write the union to 'result_directed'
        result_directed_file = output_dir / 'result_directed'
        try:
            with open(result_directed_file, 'w') as f:
                for entry in sorted(union_set):
                    f.write(f"{entry}\n")
            logging.debug("Written %d entries to '%s' (union of .slicing_func_result files).",
                        len(union_set), result_directed_file)
            log_telemetry_action(title=f"Written {len(union_set)} entries to '{result_directed_file}' (union of .slicing_func_result files).", msg_list=[], action_name="handle_slice_results", status="OK", level="verbose")
        except Exception as e:
            logging.error("Error writing result_directed file: %s", e)
            log_telemetry_action(title=f"Error writing result_directed file: {e}", msg_list=[], action_name="handle_slice_results", status="ERROR", level="debug")
            return False

        # Process verbose results for result_sarif.
        verbose_files = list(output_dir.glob('*.slicing_func_result_verbose'))
        if not verbose_files:
            logging.error(f"No '.slicing_func_result_verbose' files found in {output_dir}")
            log_telemetry_action(title=f"No '.slicing_func_result_verbose' files found in {output_dir}", msg_list=[], action_name="handle_slice_results", status="ERROR", level="debug")
            return False

        intersection_set = None
        for result_file in verbose_files:
            try:
                with open(result_file, 'r') as f:
                    file_entries = {line.strip() for line in f if line.strip()}
                logging.debug("Read %d entries from '%s'.", len(file_entries), result_file.name)
                log_telemetry_action(title=f"Read {len(file_entries)} entries from '{result_file.name}'.", msg_list=[], action_name="handle_slice_results", status="OK", level="verbose")
                if intersection_set is None:
                    intersection_set = file_entries
                else:
                    intersection_set &= file_entries
            except Exception as e:
                logging.error("Error reading file %s: %s", result_file, e)
                return False

        # Write the intersection to 'result_sarif'
        result_sarif_file = output_dir / 'result_sarif'
        try:
            with open(result_sarif_file, 'w') as f:
                for entry in sorted(intersection_set) if intersection_set is not None else []:
                    f.write(f"{entry}\n")
            count = len(intersection_set) if intersection_set is not None else 0
            logging.debug("Written %d entries to '%s' (intersection of .slicing_func_result_verbose files).",
                        count, result_sarif_file)
            log_telemetry_action(title=f"Written {count} entries to '{result_sarif_file}' (intersection of .slicing_func_result_verbose files).", msg_list=[], action_name="handle_slice_results", status="OK", level="verbose")
        except Exception as e:
            logging.error("Error writing result_sarif file: %s", e)
            log_telemetry_action(title=f"Error writing result_sarif file: {e}", msg_list=[], action_name="handle_slice_results", status="ERROR", level="debug")
            return False

        return True

    @span_decorator("merge_slice_results")
    def merge_slice_results(self):
        """
        Merges the 'result_directed' files from all harnesses into a single file.
        Creates a merged_slice_result.txt file in the slice_out directory.
        
        Returns:
            bool: True if merging is successful, False otherwise.
        """
        logging.info("Merging slice results from all harnesses")
        log_telemetry_action(title=f"Merging slice results from all harnesses", msg_list=[], action_name="merge_slice_results", status="OK", level="info")
        
        # Find all harness directories
        harness_dirs = [d for d in self.slice_out.iterdir() if d.is_dir()]
        if not harness_dirs:
            logging.error("No harness directories found for merging results")
            log_telemetry_action(title=f"No harness directories found for merging results", msg_list=[], action_name="merge_slice_results", status="ERROR", level="debug")
            return False
        log_telemetry_action(title=f"Harness directories found for merging results", msg_list=[], action_name="merge_slice_results", status="OK", level="verbose")
        # Get all result_directed files
        result_files = []
        for harness_dir in harness_dirs:
            result_file = harness_dir / 'result_directed'
            if result_file.exists():
                result_files.append(result_file)
        
        if not result_files:
            logging.error("No result_directed files found for merging")
            log_telemetry_action(title=f"No result_directed files found for merging", msg_list=[], action_name="merge_slice_results", status="ERROR", level="debug")
            return False
        log_telemetry_action(title=f"Result_directed files found for merging", msg_list=[], action_name="merge_slice_results", status="OK", level="verbose")
        # Merge all results into a single set
        merged_results = set()
        for result_file in result_files:
            try:
                with open(result_file, 'r') as f:
                    file_entries = {line.strip() for line in f if line.strip()}
                logging.debug("Read %d entries from '%s'", len(file_entries), result_file)
                log_telemetry_action(title=f"Read {len(file_entries)} entries from '{result_file}'", msg_list=[], action_name="merge_slice_results", status="OK", level="verbose")
                merged_results |= file_entries
            except Exception as e:
                logging.error("Error reading file %s: %s", result_file, e)
                log_telemetry_action(title=f"Error reading file {result_file}: {e}", msg_list=[], action_name="merge_slice_results", status="ERROR", level="debug")
                return False
        
        # Write the merged results to a file
        merged_file = self.slice_out / 'merged_slice_result.txt'
        try:
            with open(merged_file, 'w') as f:
                for entry in sorted(merged_results):
                    f.write(f"{entry}\n")
            logging.info("Written %d entries to merged result file '%s'", 
                        len(merged_results), merged_file)
            log_telemetry_action(title=f"Written {len(merged_results)} entries to merged result file '{merged_file}'", msg_list=[], action_name="merge_slice_results", status="OK", level="verbose")
            return True
        except Exception as e:
            logging.error("Error writing merged result file: %s", e)
            log_telemetry_action(title=f"Error writing merged result file: {e}", msg_list=[], action_name="merge_slice_results", status="ERROR", level="debug")
            return False

    @span_decorator("prepare_harnesses")
    def prepare_harnesses(self):
        """
        Prepares isolated directories for each harness:
        1. Finds all .bc files containing LLVMFuzzerTestOneInput function (harnesses)
        2. Extracts original source file names from the bitcode metadata
        3. Creates directories for each harness containing the harness itself and
        all other bc files except for other harnesses
        
        Returns:
            dict: Mapping of harness names to their isolated directories, or None if failed
        """
        logging.info("Preparing harness directories")
        log_telemetry_action(title=f"Preparing harness directories", msg_list=[], action_name="prepare_harnesses", status="OK", level="info")
        
        # Check if the bitcode folder exists
        if not self.slice_in.exists():
            logging.error(f"Bitcode folder not found at {self.slice_in}")
            log_telemetry_action(title=f"Bitcode folder not found at {self.slice_in}", msg_list=[], action_name="prepare_harnesses", status="ERROR", level="debug")
            return None
        log_telemetry_action(title=f"Bitcode folder found at {self.slice_in}", msg_list=[], action_name="prepare_harnesses", status="OK", level="verbose")
        # Dictionary to store harness info: {bc_file_path: original_source_file}
        harnesses = {}
        
        # List to store all BC files
        all_bc_files = []
        
        # Step 1: Find all .bc files
        logging.info("Scanning for BC files")
        log_telemetry_action(title=f"Scanning for BC files", msg_list=[], action_name="prepare_harnesses", status="OK", level="info")
        all_bc_files = list(self.slice_in.glob('**/*.bc'))
        if not all_bc_files:
            logging.error(f"No BC files found in {self.slice_in}")
            log_telemetry_action(title=f"No BC files found in {self.slice_in}", msg_list=[], action_name="prepare_harnesses", status="ERROR", level="debug")
            return None
        log_telemetry_action(title=f"BC files found in {self.slice_in}", msg_list=[], action_name="prepare_harnesses", status="OK", level="verbose")
        # Step 2: Identify harnesses and extract original source files
        logging.info("Identifying harnesses and extracting source file information")
        log_telemetry_action(title=f"Identifying harnesses and extracting source file information", msg_list=[], action_name="prepare_harnesses", status="OK", level="info")
        for bc_file in all_bc_files:
            try:
                # First check if it contains LLVMFuzzerTestOneInput
                nm_result = subprocess.run(
                    ['llvm-nm', str(bc_file)],
                    capture_output=True, 
                    text=True,
                    check=True
                )
                
                if 'LLVMFuzzerTestOneInput' not in nm_result.stdout:
                    continue  # Not a harness, skip to next file
                
                # It's a harness! Extract the original source file name using llvm-dis
                dis_result = subprocess.run(
                    ['llvm-dis', '-o', '-', str(bc_file)],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                # Parse the output to find source filename
                source_file = None
                for line in dis_result.stdout.splitlines():
                    # Look for source_filename in the LLVM IR
                    if 'source_filename =' in line:
                        # Extract quoted filename
                        parts = line.split('"')
                        if len(parts) >= 2:
                            source_file = parts[1]
                            break
                
                if source_file:
                    # Store just the base filename without path or extension
                    harness_source_basename = Path(source_file).stem
                    harnesses[bc_file] = harness_source_basename
                    logging.debug(f"Found harness in {bc_file.name}, source file: {harness_source_basename}")
                    log_telemetry_action(title=f"Found harness in {bc_file.name}, source file: {harness_source_basename}", msg_list=[], action_name="prepare_harnesses", status="OK", level="verbose")
                else:
                    logging.warning(f"Could not extract source filename from {bc_file}")
                    log_telemetry_action(title=f"Could not extract source filename from {bc_file}", msg_list=[], action_name="prepare_harnesses", status="ERROR", level="debug")
            except subprocess.SubprocessError as e:
                logging.error(f"Error analyzing BC file {bc_file}: {e}")
                log_telemetry_action(title=f"Error analyzing BC file {bc_file}: {e}", msg_list=[], action_name="prepare_harnesses", status="ERROR", level="debug")
                continue
                
        if not harnesses:
            logging.error("No harness files found")
            log_telemetry_action(title=f"No harness files found", msg_list=[], action_name="prepare_harnesses", status="ERROR", level="debug")
            return None
            
        logging.info(f"Found {len(harnesses)} harness files")
        log_telemetry_action(title=f"Found {len(harnesses)} harness files", msg_list=[], action_name="prepare_harnesses", status="OK", level="verbose")
        # Step 3: Create isolated directories for each harness
        log_telemetry_action(title=f"Creating isolated directories for each harness", msg_list=list(harnesses.items()), action_name="prepare_harnesses", status="OK", level="info")
        harness_dirs = {}
        for harness_path, harness_source_basename in harnesses.items():
            # Create directory using just the basename of the source file
            harness_dir = self.slice_work / harness_source_basename
            harness_dir.mkdir(exist_ok=True)
            harness_dirs[harness_source_basename] = harness_dir
            
            # Copy the harness file to the directory
            dest_path = harness_dir / harness_path.name
            try:
                import shutil
                shutil.copy2(harness_path, dest_path)
                logging.debug(f"Copied harness {harness_path.name} to {harness_dir}")
                log_telemetry_action(title=f"Copied harness {harness_path.name} to {harness_dir}", msg_list=[], action_name="prepare_harnesses", status="OK", level="verbose")
                # Copy all other BC files except for other harnesses
                for bc_path in all_bc_files:
                    # Skip other harnesses
                    if bc_path in harnesses and bc_path != harness_path:
                        continue
                        
                    # Copy the BC file
                    bc_dest = harness_dir / bc_path.name
                    shutil.copy2(bc_path, bc_dest)
                    
                logging.debug(f"Copied dependent BC files to {harness_dir}")
            except Exception as e:
                logging.error(f"Error creating harness directory for {harness_source_basename}: {e}")
                log_telemetry_action(title=f"Error creating harness directory for {harness_source_basename}: {e}", msg_list=[], action_name="prepare_harnesses", status="ERROR", level="debug")
                continue
                
        logging.info(f"Created {len(harnesses)} harness directories")
        log_telemetry_action(title=f"Created {len(harnesses)} harness directories", msg_list=[], action_name="prepare_harnesses", status="OK", level="verbose")
        return harness_dirs