import re
import logging
import subprocess
from pathlib import Path
import hashlib

from daemon.modules.workspace import WorkspaceManager
from daemon.modules.diff_parser import DiffParser

class PatchManager:
    def __init__(self, workspace_manager: WorkspaceManager):
        """
        Initializes the PatchManager with a WorkspaceManager instance.
        
        Args:
            workspace_manager (WorkspaceManager): An instance managing your workspace.
        """
        self.workspace_manager = workspace_manager
        
        # Retrieve the focused repository from the workspace.
        focused_repo = self.workspace_manager.get_focused_repo()
        if not focused_repo:
            raise ValueError("Focused repository not found in the workspace.")
        
        # Retrieve the diff file path from the workspace manager.
        self.diff_path = self.workspace_manager.diff_path
        self.focused_repo = Path(focused_repo)

        # Instantiate the DiffParser for analysis tasks
        self.diff_parser = DiffParser(workspace_manager)

    def get_modified_functions(self, use_new_code=True):
        """
        Retrieves the list of modified functions using DiffParser.

        Args:
            use_new_code (bool): Passed to DiffParser to determine which file version's
                                 line numbers to use. Defaults to True.

        Returns:
            list: A list of unique tuples (absolute_file_path, function_name)
                  as returned by DiffParser. Returns an empty list on error.
        """
        try:
            return self.diff_parser.get_modified_functions(use_new_code=use_new_code)
        except Exception as e:
             logging.error(f"Error retrieving modified functions via DiffParser: {e}")
             # Depending on desired behavior, you might re-raise or return empty
             return []

    def transform_results_with_md5(self, patch_results):
        """
        Transforms the modified functions results by replacing file paths with their MD5 checksums.
        
        This function:
        1. Takes the results from get_modified_functions
        2. Calculates MD5 checksums for each modified file
        3. Transforms the results format from (file_path, function_name) tuples 
           to [<md5_sum>, function_name] lists
        
        Args:
            patch_results (list): List of (file_path, function_name) tuples from get_modified_functions
            
        Returns:
            list: Transformed list with [<md5_sum>, function_name] pairs
        """
        updated_results = []
        
        for file_path, function_name in patch_results:
            try:
                # Convert file_path to Path if it's not already
                full_path = Path(file_path)
                if not full_path.is_absolute():
                    full_path = self.focused_repo / file_path
                
                # Check if file exists
                if not full_path.exists():
                    logging.warning(f"File {full_path} does not exist, skipping MD5 calculation")
                    # Extract just the filename without path for the result
                    updated_results.append([full_path.name, function_name])
                    continue
                    
                # Calculate MD5 checksum
                md5_hash = hashlib.md5()
                with open(full_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        md5_hash.update(chunk)
                
                md5_sum = md5_hash.hexdigest()
                
                # Update the file path to just the MD5 sum
                updated_results.append([md5_sum, function_name])
                
            except Exception as e:
                logging.exception(f"Error calculating MD5 for {file_path}: {e}")
                # Keep just the filename if there's an error
                if isinstance(file_path, Path):
                    updated_results.append([file_path.name, function_name])
                else:
                    updated_results.append([Path(file_path).name, function_name])
        
        return updated_results

    def apply_patch(self, patch_file = None):
        """
        Applies the given patch file to the focused repository.
        
        Args:
            patch_file (str or Path): Path to the patch file. If None, uses the
                                      diff_path from the WorkspaceManager.
        
        Returns:
            bool: True if the patch was applied successfully; False otherwise.
        """
        if patch_file is None:
            patch_file = self.diff_path
            if not patch_file:
                logging.error("No patch file specified or found in WorkspaceManager.")
                return False
            if not Path(patch_file).is_file():
                 logging.error(f"Patch file specified does not exist: {patch_file}")
                 return False

        try:
            # Ensure the target directory exists
            if not self.focused_repo.is_dir():
                 logging.error(f"Focused repository directory does not exist: {self.focused_repo}")
                 return False

            cmd = ["patch", "-p1", "-i", str(patch_file)]
            # Run the patch command in the directory of the focused repo.
            logging.info(f"Applying patch '{patch_file}' in '{self.focused_repo}'...")
            result = subprocess.run(cmd, cwd=str(self.focused_repo),
                                    capture_output=True, text=True, check=False) # Use check=False to handle errors manually

            if result.returncode != 0:
                # Log detailed error information
                logging.error(f"Error applying patch '{patch_file}' to '{self.focused_repo}'. Return code: {result.returncode}")
                logging.error(f"Stdout: {result.stdout}")
                logging.error(f"Stderr: {result.stderr}")
                # Consider attempting a reverse patch or other recovery mechanism here if needed
                return False

            logging.info(f"Patch '{patch_file}' applied successfully to '{self.focused_repo}'.")
            return True
        except FileNotFoundError:
             logging.error("The 'patch' command was not found. Please ensure it's installed and in the system's PATH.")
             return False
        except Exception as e:
            logging.exception(f"An unexpected exception occurred while applying patch '{patch_file}' to '{self.focused_repo}': {e}")
            return False
