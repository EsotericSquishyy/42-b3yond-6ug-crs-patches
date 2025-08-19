import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PatchManager:
    @staticmethod
    async def apply_patch(project_dir: Path, diff_path: Path) -> bool:
        try:
            diff_file = diff_path / 'ref.diff'

            # If ref.diff doesn't exist, find all *.diff files
            if not diff_file.exists():
                logger.info(
                    f"ref.diff not found in {diff_path}, looking for other diff files")
                diff_files = list(diff_path.glob('*.diff'))

                if not diff_files:
                    logger.error(f"No diff files found in {diff_path}")
                    return False

                # Apply each diff file one by one
                for df in diff_files:
                    logger.info(f"Applying patch from {df}")
                    cmd = ['patch', '-p1', '-i', str(df)]
                    process = subprocess.Popen(
                        cmd,
                        cwd=str(project_dir),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    stdout, stderr = process.communicate()

                    if process.returncode != 0:
                        logger.error(
                            f"Patch failed for {df}: {stderr.decode()}")
                        return False

                    logger.info(f"Patch from {df.name} applied successfully")

                return True
            else:
                # Original behavior for ref.diff
                cmd = ['patch', '-p1', '-i', str(diff_file)]
                process = subprocess.Popen(
                    cmd,
                    cwd=str(project_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate()

                if process.returncode != 0:
                    logger.error(f"Patch failed: {stdout} \n{stderr}")
                    return False

                logger.info(f"Patch applied successfully: {stdout.decode()}")
                return True

        except Exception as e:
            logger.error(f"Error applying patch: {str(e)}")
            return False
