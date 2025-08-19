import shutil
import tarfile
import logging
from pathlib import Path
import uuid
from daemon.slice_msg import SliceMsg
from utils.misc import safe_extract_tar

from daemon.modules.telemetry import log_telemetry_action

class WorkspaceManager:
    def __init__(self, base_dir, msg: SliceMsg):
        """
        Initializes the WorkspaceManager.
        
        Args:
            base_dir (str): The base directory for workspaces.
            msg (DirectedMsg): The incoming message containing repository info.
        """
        self.base_dir = Path(base_dir).resolve()
        self.msg = msg
        tmp_dir = Path('/tmp').resolve()

        # Security check: Ensure base_dir is within /tmp to prevent accidental data loss.
        try:
            self.base_dir.relative_to(tmp_dir)
        except ValueError:
            raise ValueError(f'Attempt to use non-tmp dir {self.base_dir} as workspace')

    def __enter__(self):
        """Create and return a workspace for processing a work unit."""
        self.worker_id = str(uuid.uuid4())
        self.workspace_dir = self.base_dir / self.worker_id

        try:
            self.create_workspace()
        except Exception as e:
            logging.exception(f"Failed to create workspace for {self.worker_id}: {e}")
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Called when the workspace work is finished."""
        if exc_type:
            logging.error(f"Error occurred in workspace {self.worker_id}: {exc_value}")
        else:
            logging.info(f"Work finished for worker {self.worker_id}. Check {self.workspace_dir} for details.")
        # Optionally cleanup here or leave the workspace for further inspection.
        # self.cleanup_workspace()

    def create_workspace(self):
        """Creates the workspace directory, cleaning up any preexisting directory."""
        if not hasattr(self, 'worker_id'):
            raise ValueError('Workspace must be created within a "with" statement.')

        logging.info(f'Assigned worker_id: {self.worker_id} with work_dir: {self.workspace_dir}')
        if self.workspace_dir.exists():
            logging.info(f"Cleaning up preexisting workspace: {self.workspace_dir}")
            shutil.rmtree(self.workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        return self.workspace_dir

    def cleanup_workspace(self):
        """Deletes the workspace directory."""
        if self.workspace_dir.exists():
            try:
                shutil.rmtree(self.workspace_dir)
                logging.info(f'Successfully removed workspace directory: {self.workspace_dir}')
            except Exception as e:
                logging.error(f'Error removing workspace directory {self.workspace_dir}: {e}')
                raise
        
    def cleanup_basedir(self):
        """Cleans the entire base_dir, removing all workspaces."""
        if self.base_dir.exists():
            try:
                shutil.rmtree(self.base_dir)
                logging.warning(f'All workspaces removed! Base directory {self.base_dir} has been deleted!')
            except Exception as e:
                logging.error(f'Error removing base directory {self.base_dir}: {e}')
                raise
        else:
            logging.warning(f'Base directory {self.base_dir} does not exist!')

    def copy_and_extract_repos(self):
        """
        Copies and extracts all repositories provided in the message.
        Expects msg.repo, msg.diff, and msg.fuzzing_tooling to be defined.
        """
        # --- Process the 'diff' attribute ---
        diff_value = getattr(self.msg, 'diff', None)
        if diff_value:
            # If multiple diff repos are provided, use the first one.
            diff_value = diff_value[0] if isinstance(diff_value, list) else diff_value
            diff_repo_path = Path(diff_value)
            diff_tar_path = self.workspace_dir / diff_repo_path.name

            try:
                shutil.copy2(diff_repo_path, diff_tar_path)
                logging.debug(f"Copied diff repo {diff_repo_path} to workspace at {diff_tar_path}")
            except Exception as e:
                logging.error(f"Failed to copy diff repo {diff_repo_path}: {e}")
                raise

            if tarfile.is_tarfile(diff_tar_path):
                # Extract the tar file into its own subdirectory using the full name
                diff_extracted = self.workspace_dir / f"{diff_repo_path.name}_extracted"
                diff_extracted.mkdir(exist_ok=True)
                try:
                    safe_extract_tar(diff_tar_path, diff_extracted)
                except Exception as e:
                    logging.error(f"Error extracting tarfile {diff_tar_path}: {e}")
                    raise
                # Probe the first-level directory from the extracted content.
                diff_base = self.get_first_level_dir(diff_extracted)
                self.diff_path = self.find_diff_file(diff_base)
                if not self.diff_path:
                    logging.error("No .diff file found under the diff repository")
                    raise FileNotFoundError("No .diff file found under the diff repository")
            else:
                # if diff_tar_path.is_dir():
                #     diff_base = self.get_first_level_dir(diff_tar_path)
                #     self.diff_path = self.find_diff_file(diff_base)
                # else:
                #     logging.error("diff repository is not a tar file and not a directory")
                # ? Now we do not accept diff as a directory
                logging.error("diff repository is not a tar file")
                raise Exception("Invalid diff repository format")
        else:
            if getattr(self.msg, 'is_sarif', None) == True:
                logging.warning("diff attribute is not defined in message, but is_sarif is True. Proceeding without diff.")
            else:
                # If is_sarif is not True, we raise an error.
                logging.error("diff attribute is not defined in message.")
                raise Exception("diff attribute is not defined in message.")

        # --- Process the 'fuzzing_tooling' attribute ---
        ft_value = getattr(self.msg, 'fuzzing_tooling', None)
        if ft_value:
            # Use the first repository if multiple are provided.
            ft_value = ft_value[0] if isinstance(ft_value, list) else ft_value
            ft_repo_path = Path(ft_value)
            ft_tar_path = self.workspace_dir / ft_repo_path.name

            try:
                shutil.copy2(ft_repo_path, ft_tar_path)
                logging.debug(f"Copied fuzzing_tooling repo {ft_repo_path} to workspace at {ft_tar_path}")
            except Exception as e:
                logging.error(f"Failed to copy fuzzing_tooling repo {ft_repo_path}: {e}")
                raise

            if tarfile.is_tarfile(ft_tar_path):
                # Extract the tar file into its own subdirectory using the full name
                ft_extracted = self.workspace_dir / f"{ft_repo_path.name}_extracted"
                ft_extracted.mkdir(exist_ok=True)
                try:
                    safe_extract_tar(ft_tar_path, ft_extracted)
                except Exception as e:
                    logging.error(f"Error extracting tarfile {ft_tar_path}: {e}")
                    raise
                # Probe the first-level directory from the extracted content.
                ft_base = self.get_first_level_dir(ft_extracted)
                self.helper_path = self.find_helper_in_infra(ft_base)
                self.fuzzing_tooling_path = self.helper_path.parent.parent
                if not self.helper_path:
                    logging.error("helper.py not found under an 'infra' directory within fuzzing_tooling repository")
                    raise FileNotFoundError("helper.py not found under an 'infra' directory within fuzzing_tooling repository")
            else:
                # if ft_tar_path.is_dir():
                #     ft_base = self.get_first_level_dir(ft_tar_path)
                #     self.helper_path = self.find_helper_in_infra(ft_base)
                # else:
                #     logging.error("fuzzing_tooling repository is not a tar file and not a directory")
                # ? Now we do not accept fuzzing_tooling as a directory
                logging.error("fuzzing_tooling repository is not a tar file")
                raise Exception("Invalid fuzzing_tooling repository format")
        else:
            logging.error("fuzzing_tooling attribute is not defined in message.")
            raise Exception("fuzzing_tooling attribute is not defined in message.")

        # --- Process the 'repo' attribute ---
        repo_value = getattr(self.msg, 'repo', None)
        if repo_value:
            items = repo_value if isinstance(repo_value, list) else [repo_value]
            for repo in items:
                repo_path = Path(repo)
                dest_path = self.workspace_dir / repo_path.name

                try:
                    shutil.copy2(repo_path, dest_path)
                    logging.debug(f"Copied repo {repo_path} to workspace at {dest_path}")
                except Exception as e:
                    logging.error(f"Failed to copy repo {repo_path}: {e}")
                    raise

                if tarfile.is_tarfile(dest_path):
                    try:
                        safe_extract_tar(dest_path, self.workspace_dir)
                    except Exception as e:
                        logging.error(f"Error extracting tarfile {dest_path}: {e}")
                        raise
        else:
            logging.error("repo attribute is not defined in message.")
            raise Exception("repo attribute is not defined in message.")

    def get_first_level_dir(self, extracted_dir: Path) -> Path:
        """
        Returns the first-level directory within the extracted directory.
        If exactly one subdirectory exists, that directory is returned.
        If multiple exist, a warning is logged and the first one is returned.
        If none exist, the extracted_dir itself is returned.
        """
        subdirs = [p for p in extracted_dir.iterdir() if p.is_dir()]
        if len(subdirs) == 1:
            return subdirs[0]
        elif subdirs:
            logging.warning(f"Multiple top-level directories found in {extracted_dir}. Using the first one: {subdirs[0]}")
            return subdirs[0]
        else:
            return extracted_dir

    def find_helper_in_infra(self, base_dir: Path):
        """
        Searches for helper.py in any directory named 'infra' under the specified base_dir.
        
        Args:
            base_dir (Path): The directory under which to search.
            
        Returns:
            The resolved path to helper.py if found, otherwise None.
        """
        for path in base_dir.rglob("helper.py"):
            if path.parent.name == "infra":
                return path.resolve()
        return None

    def find_diff_file(self, base_dir: Path):
        """
        Searches for files ending with '.diff' under the specified base_dir.
        
        Args:
            base_dir (Path): The directory under which to search.
        
        Returns:
            The resolved path to the first .diff file found. If multiple are found, a warning is logged.
            Returns None if no .diff file is found.
        """
        diff_files = list(base_dir.rglob("*.diff"))
        if not diff_files:
            return None
        if len(diff_files) > 1:
            logging.warning(f"Multiple .diff files found under {base_dir}. Using the first one: {diff_files[0]}")
        return diff_files[0].resolve()
    
    def get_focused_repo(self):
        """Retrieve a specific focused repository"""
        focused_repo = self.workspace_dir / self.msg.focus
        if not focused_repo.exists():
            logging.error(f"Focused repo {focused_repo} does not exist.")
            return None

        return focused_repo
