import re
import logging
import subprocess
from pathlib import Path

from daemon.modules.workspace import WorkspaceManager

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
        if not hasattr(self.workspace_manager, 'diff_path'):
            self.diff_path = None
        else:
            self.diff_path = self.workspace_manager.diff_path
        self.focused_repo = Path(focused_repo)

    def extract_function_from_hunk_header(self, line):
        """
        Given a diff hunk header line, attempt to extract the function signature,
        then extract the function name.
        """
        m = re.match(r"@@.*@@\s*(.*)", line)
        if m:
            signature = m.group(1).strip()
            if signature:
                return self.extract_function_from_signature(signature)
        return None

    def extract_function_from_signature(self, signature):
        """
        Extracts the function name from a signature.
        E.g., "static int my_function(int a, int b)" → "my_function"
        """
        m = re.search(r'([A-Za-z_]\w*)\s*\(', signature)
        if m:
            return m.group(1)
        return None

    def extract_function_from_accumulation(self, accum):
        """
        When added code spans multiple lines, attempt to extract a complete function definition.
        """
        pattern = re.compile(r'^\s*(?:[\w\*\s]+)\s+([A-Za-z_]\w*)\s*\([^;{]*\)\s*\{', re.DOTALL)
        m = pattern.search(accum)
        if m:
            return m.group(1)
        return None

    def analyze_patch(self, diff_file=None):
        """
        Analyzes the diff file and returns a set of function names that appear to be changed.
        
        Args:
            diff_file (str or Path, optional): Path to the diff file.
                If not provided, uses the diff_path from the WorkspaceManager.
        
        Returns:
            set: A set of function names extracted from the diff.
        """
        if diff_file is None:
            diff_file = self.diff_path

        changed_functions = set()
        try:
            with open(diff_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            logging.error("Error reading diff file: %s", e)
            return changed_functions

        accum = ""
        accumulating = False
        for line in lines:
            if line.startswith("@@"):
                func = self.extract_function_from_hunk_header(line)
                if func:
                    changed_functions.add(func)
                # End accumulation when a new hunk header is reached.
                if accum:
                    new_func = self.extract_function_from_accumulation(accum)
                    if new_func:
                        changed_functions.add(new_func)
                    accum = ""
                    accumulating = False
            elif line.startswith('+') and not line.startswith("+++"):
                content = line[1:]  # Remove the '+' diff marker.
                accum += content
                accumulating = True
                # If accumulated text seems complete, try to extract a function.
                if '{' in content and ')' in accum:
                    new_func = self.extract_function_from_accumulation(accum)
                    if new_func:
                        changed_functions.add(new_func)
                        accum = ""
                        accumulating = False
            else:
                if accumulating and accum:
                    new_func = self.extract_function_from_accumulation(accum)
                    if new_func:
                        changed_functions.add(new_func)
                    accum = ""
                    accumulating = False
        # Check for any trailing accumulated text.
        if accumulating and accum:
            new_func = self.extract_function_from_accumulation(accum)
            if new_func:
                changed_functions.add(new_func)
        return changed_functions

    def apply_patch(self, patch_file = None):
        """
        Applies the given patch file to the focused repository.
        
        Args:
            patch_file (str or Path): Path to the patch file.
        
        Returns:
            bool: True if the patch was applied successfully; False otherwise.
        """
        if patch_file is None:
            patch_file = self.diff_path

        try:
            cmd = ["patch", "-p1", "-i", str(patch_file)]
            # Run the patch command in the directory of the focused repo.
            result = subprocess.run(cmd, cwd=str(self.focused_repo),
                                    capture_output=True, text=True)
            if result.returncode != 0:
                logging.exception("Error applying patch < %s | %s >: %s", str(patch_file), str(self.focused_repo), result.stdout)
                return False
            logging.info("Patch applied successfully.")
            return True
        except Exception as e:
            logging.exception("Exception applying patch: %s", e)
            return False
