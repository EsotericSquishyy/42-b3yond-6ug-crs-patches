import logging
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from modules.file_manager import FileManager
from modules.config import Config
from modules.redis_middleware import RedisMiddleware

logger = logging.getLogger(__name__)


class ArtifactBackup:
    """
    Handles backing up source code and build artifacts to a permanent storage location.
    """

    def __init__(self, src_path: Path, oss_fuzz_path: Path, config: Config = None):
        """
        Initialize the ArtifactBackup class.

        Args:
            src_path: Path to the source code
            oss_fuzz_path: Path to the OSS-Fuzz directory
            config: Configuration object, if None will load from env
        """
        self.src_path = Path(src_path)
        self.oss_fuzz_path = Path(oss_fuzz_path)
        self.config = config or Config.from_env()
        self.file_manager = FileManager()

    async def backup_artifacts(self, project_name: str) -> Dict[str, Any]:
        """
        Backup source code and build artifacts.

        Args:
            project_name: Name of the project being backed up

        Returns:
            Dict with information about the backup operation
        """
        try:
            # Create backup directory
            task_id = self.oss_fuzz_path.parent.name
            backup_root = Path(self.config.crs_mount_path) / \
                'public_build' / task_id
            backup_root.mkdir(parents=True, exist_ok=True)

            # Create specific directories
            src_backup_dir = backup_root / 'src'
            build_backup_dir = backup_root / 'build'

            # Backup source code
            src_backup_dir.mkdir(parents=True, exist_ok=True)
            self.file_manager.copy_via_tar_archive(str(self.src_path), str(src_backup_dir))
            logger.info(f"Source code backed up to {src_backup_dir}")

            # Backup build artifacts
            build_backup_dir.mkdir(parents=True, exist_ok=True)
            build_src_dir = self.oss_fuzz_path / 'build'

            # Copy out directory (contains compiled binaries)
            out_dir = build_src_dir / 'out' / project_name
            if out_dir.exists():
                self.file_manager.copy_via_tar_archive(
                    str(out_dir), str(build_backup_dir / 'out'))
                logger.info(
                    f"Build artifacts backed up to {build_backup_dir / 'out'}")

            result = {
                "status": "success",
                "backup_path": str(backup_root),
                "src_backup": str(src_backup_dir),
                "build_backup": str(build_backup_dir),
                "project_name": project_name
            }

            # Record backup info in Redis
            redis_client = RedisMiddleware()
            await redis_client.record_public_backup(task_id, result)
            logger.info(
                f"Backup information recorded in Redis for task {task_id}")

            return result

        except Exception as e:
            logger.error(f"Failed to backup artifacts: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    def _copy_directory(self, src: Path, dest: Path) -> None:
        """
        Copy directory contents, creating destination if needed.

        Args:
            src: Source directory path
            dest: Destination directory path
        """
        dest.mkdir(parents=True, exist_ok=True)

        try:
            if src.is_file():
                shutil.copy2(src, dest)
            else:
                # Instead of using copytree, manually walk the directory
                # to handle missing files and symbolic links better
                for item in src.glob('**/*'):
                    # Get the relative path from the source root
                    rel_path = item.relative_to(src)
                    target_path = dest / rel_path
                    
                    # Create parent directories if needed
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Skip if source doesn't exist anymore (might have been deleted)
                    if not item.exists():
                        logger.debug(f"Skipping non-existent path: {item}")
                        continue
                    
                    # Handle symbolic links
                    if item.is_symlink():
                        # Get the symlink target
                        link_target = item.readlink()
                        # Create a similar symlink at the destination
                        # First remove the target if it exists
                        if target_path.exists() or target_path.is_symlink():
                            target_path.unlink()
                        target_path.symlink_to(link_target)
                        logger.debug(f"Created symlink at {target_path} pointing to {link_target}")
                    # Copy files
                    elif item.is_file():
                        try:
                            shutil.copy2(item, target_path)
                        except (FileNotFoundError, PermissionError) as e:
                            logger.debug(f"Could not copy {item}: {e}")
                    # Create directories (already handled by parent.mkdir above)
                    elif item.is_dir():
                        target_path.mkdir(parents=True, exist_ok=True)
                
                logger.info(f"Directory {src} copied to {dest}")
        except Exception as e:
            logger.warning(f"Error copying {src} to {dest}: {e}")
            # No need for the fallback approach since we're using our own custom traversal

    def get_backup_location(self, task_id: str) -> Path:
        """
        Get the backup directory path for a given task ID.

        Args:
            task_id: Task identifier

        Returns:
            Path to the backup directory
        """
        return Path(self.config.crs_mount_path) / 'public_build' / task_id
