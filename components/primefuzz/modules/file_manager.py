import os
import shutil
import traceback
import subprocess
import tempfile
import shutil
import time
import aiohttp
import tarfile
import logging
import zipfile
import base64
from pathlib import Path
from urllib.parse import urlparse
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# 0000: 8950 4e47 0d0a 1a0a 0000 000d 4948 4452  .PNG........IHDR
# 0010: 0000 0020 0000 00                        ... ...
SAMPLE_BLOB_B64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAA"


def create_a_simple_seed_corpus(corpus_dir: Path) -> None:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    seed_file = corpus_dir / "aixcc_sample.bin"
    logger.debug(f"Creating a simple seed corpus: {seed_file}")
    seed_file.write_bytes(base64.b64decode(SAMPLE_BLOB_B64))


def delete_folder(folder_path: Path) -> None:
    """Delete a folder and its contents."""
    if folder_path.exists():
        shutil.rmtree(folder_path, ignore_errors=True)
        logger.info(f"Deleted folder: {folder_path}")
    else:
        logger.warning(f"Folder not found: {folder_path}")


class FileManager:
    def _is_url(self, path: str) -> bool:
        """Check if path is a URL."""
        try:
            result = urlparse(path)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    async def download_sources(self, sources: List[Dict], task_dir: Path) -> List[Path]:
        downloaded_files = []
        try:
            async with aiohttp.ClientSession() as session:
                for source in sources:
                    try:
                        url = source["url"]
                        file_type = source["type"]
                        output_path = task_dir / f"{file_type}.tar.gz"
                        task_dir.mkdir(parents=True, exist_ok=True)

                        if self._is_url(url):
                            # Handle remote URL
                            async with session.get(url) as response:
                                response.raise_for_status()
                                content = await response.read()
                                output_path.write_bytes(content)
                        else:
                            # Handle local path
                            src_path = Path(url)
                            if not src_path.exists():
                                raise FileNotFoundError(
                                    f"Local file not found: {url}")
                            output_path = self.copy_file(
                                src_path, task_dir, f"{file_type}.tar.gz"
                            )

                        if output_path:
                            downloaded_files.append(output_path)

                    except (KeyError, aiohttp.ClientError, IOError) as e:
                        logger.error(
                            f"Error downloading source {source}: {str(e)}")
                        continue

        except Exception as e:
            logger.error(f"Failed to download sources: {str(e)}")
            return []

        return downloaded_files

    def create_or_get_shared_task_dir(self, task_id: str) -> Path:
        shared_crs_dir = os.getenv("CRS_MOUNT_PATH", "/crs")
        instance_id = os.getenv("INSTANCE_ID", "default")
        task_dir = Path(shared_crs_dir) / "primetasks" / instance_id / task_id
        if not task_dir.exists():
            task_dir.mkdir(parents=True, exist_ok=True)

        return task_dir

    def create_task_directory(self, task_id: str) -> Path:
        if os.getenv("ENABLE_SHARED_CRS"):
            shared_crs_dir = os.getenv("CRS_MOUNT_PATH", "/tmp")
        else:
            logger.info(
                "Using local directory for task storage.")
            shared_crs_dir = "/tmp"
        instance_id = os.getenv("INSTANCE_ID", "default")
        task_dir = Path(shared_crs_dir) / "primetasks" / instance_id / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    def get_task_directory(self, task_id: str) -> Path:
        if os.getenv("ENABLE_SHARED_CRS"):
            shared_crs_dir = os.getenv("CRS_MOUNT_PATH", "/tmp")
        else:
            shared_crs_dir = "/tmp"
        instance_id = os.getenv("INSTANCE_ID", "default")
        task_dir = Path(shared_crs_dir) / "primetasks" / instance_id / task_id
        return task_dir

    def get_file_info(self, file_path: Path) -> Dict:
        return {
            "name": file_path.name,
            "size": file_path.stat().st_size,
            "owner": file_path.owner(),
        }

    def extract_archive(self, file_path: Path, extract_dir: Path) -> Path:
        extract_dir.mkdir(parents=True, exist_ok=True)

        if file_path.suffix in [".tar", ".gz", ".tgz"]:
            with tarfile.open(file_path) as tar:
                # Get first member path with normalization
                first_dir = None
                for member in tar.getmembers():
                    if member.isdir():
                        # Normalize path to remove ./ and split
                        normalized_path = os.path.normpath(member.name)
                        first_dir = extract_dir / normalized_path.split("/")[0]
                        if not first_dir.name.startswith("."):
                            break

                # Extract archive
                tar.extractall(path=extract_dir)

                # Return first directory if found
                if first_dir and first_dir.exists():
                    return first_dir

        return extract_dir
    
    def sync_directories(
        self, src_dir: Path, dest_dir: Path, exclude: List[str] = None):
        """Sync source directory to destination with rsync.
        Args:
            src_dir: Source directory to sync
            dest_dir: Destination directory
            exclude: List of patterns to exclude from syncing
        
            for example: to copy from /crs/primetasks/oss-fuzz/build/out/$project_name to /tmp/primetasks/oss-fuzz/build/out/$project_name
            1. clear target directory at first
            2. rsync from source to target
        """
        try:
            if not src_dir.exists():
                raise FileNotFoundError(f"Source directory not found: {src_dir}")
            
            # Create destination parent directory if it doesn't exist
            dest_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # Clear target directory if it exists
            if dest_dir.exists():
                logger.info(f"Clearing destination directory: {dest_dir}")
                shutil.rmtree(dest_dir)
            
            # Create the destination directory
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            # Prepare rsync command
            rsync_cmd = ['rsync', '-a', '--delete']
            
            # Add exclude patterns if provided
            if exclude:
                for pattern in exclude:
                    rsync_cmd.extend(['--exclude', pattern])
            
            # Add source and destination paths
            src_path = str(src_dir) + '/'  # trailing slash to copy contents
            dest_path = str(dest_dir)
            rsync_cmd.extend([src_path, dest_path])
            
            logger.debug(f"Executing rsync command: {' '.join(rsync_cmd)}")
            
            # Execute rsync
            result = subprocess.run(
                rsync_cmd,
                check=True,
                capture_output=True,
                text=True
            )
            
            logger.info(f"Successfully synced {src_dir} to {dest_dir}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Rsync failed: {e}")
            logger.error(f"Command: {' '.join(e.cmd)}")
            logger.error(f"Stderr: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Error syncing directories {src_dir} to {dest_dir}: {e}")
            logger.error(traceback.format_exc())
            return False

    def copy_file(
        self, src_file_path: Path, dest_dir: Path, dest_name: str = None
    ) -> Optional[Path]:
        """Copy single file to destination directory with optional renaming.

        Args:
            src_file_path: Source file to copy
            dest_dir: Destination directory
            dest_name: Optional new name for destination file

        Returns:
            Path: Path to copied file, None if error
        """
        try:
            if not src_file_path.is_file():
                raise FileNotFoundError(
                    f"Source file not found: {src_file_path}")

            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / \
                (dest_name if dest_name else src_file_path.name)

            shutil.copy2(src_file_path, dest_path)
            logger.debug(f"Successfully copied {src_file_path} to {dest_path}")
            return dest_path

        except Exception as e:
            logger.error(
                f"Error copying file {src_file_path} to {dest_dir}: {e}")
            return None

    def copy_via_tar_archive(self, src_dir: str, dst_dir: str):
        """
        Copies a source directory to a destination directory, optimized for scenarios
        with many small files over network filesystems like NFS.

        It works by:
        1. Creating a temporary tar archive of the source directory locally.
        2. Copying the single large archive file to the destination directory.
        3. Extracting the archive in the destination directory.
        4. Cleaning up the temporary archives.

        Requires the 'tar' command-line utility to be available.

        Args:
            src_dir: The absolute path to the source directory.
            dst_dir: The absolute path to the destination directory. The target
                    directory structure (up to the final component) should exist.
                    The final component (basename of src_dir) will be created
                    inside dst_dir.

        Returns:
            True if successful, False otherwise.
        """
        if not os.path.isdir(src_dir):
            logger.error(f"Source directory not found or is not a directory: {src_dir}")
            return False

        # Ensure the parent of the final destination exists
        # e.g., if copying '/tmp/data' to '/nfs/backup/', ensure '/nfs/backup/' exists.
        # The function will create '/nfs/backup/data/' based on the source basename.
        final_destination_path = os.path.join(dst_dir, os.path.basename(os.path.abspath(src_dir)))

        if not os.path.isdir(dst_dir):
            try:
                # Attempt to create the base destination directory if it doesn't exist
                os.makedirs(dst_dir, exist_ok=True)
                logger.info(f"Base destination directory created: {dst_dir}")
            except OSError as e:
                logger.error(f"Failed to create base destination directory {dst_dir}: {e}")
                return False

        # Use NamedTemporaryFile for safer handling of temp files
        temp_archive_file = None
        archive_on_dest_path = None
        success = False

        try:
            # 1. Create a temporary tar archive locally
            logger.info(f"Creating temporary archive from: {src_dir}")
            start_time = time.time()
            # Create temp file - deleted automatically on close unless delete=False
            with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as temp_f:
                temp_archive_file = temp_f.name

            # Important: Use -C to change directory so the archive contains relative paths
            src_parent = os.path.dirname(os.path.abspath(src_dir))
            src_basename = os.path.basename(os.path.abspath(src_dir))

            # Use Popen for potentially better handling of large outputs/errors if needed
            # but run() with check=True is simpler for PoC
            # Example: tar cf /tmp/tmpxxxxxx.tar -C /path/to/source/.. source_dir_name
            create_cmd = ['tar', 'cf', temp_archive_file, '-C', src_parent, src_basename]
            logger.debug(f"Executing: {' '.join(create_cmd)}")
            result = subprocess.run(create_cmd, check=True, capture_output=True, text=True)
            logger.info(f"Archive created: {temp_archive_file} (took {time.time() - start_time:.2f}s)")

            # 2. Copy the single archive file to the destination
            logger.info(f"Copying archive to destination: {dst_dir}")
            start_time = time.time()
            # Define where the archive will land on the destination side
            archive_on_dest_path = os.path.join(dst_dir, os.path.basename(temp_archive_file))
            shutil.copy2(temp_archive_file, archive_on_dest_path) # copy2 preserves metadata
            logger.info(f"Archive copied to {archive_on_dest_path} (took {time.time() - start_time:.2f}s)")

            # 3. Extract the archive in the destination directory
            logger.info(f"Extracting archive at destination: {archive_on_dest_path}")
            start_time = time.time()
            # Example: tar xf /nfs/backup/tmpxxxxxx.tar -C /nfs/backup/
            extract_cmd = ['tar', 'xf', archive_on_dest_path, '-C', dst_dir]
            logger.debug(f"Executing: {' '.join(extract_cmd)}")
            result = subprocess.run(extract_cmd, check=True, capture_output=True, text=True)
            logger.info(f"Archive extracted in {dst_dir} (took {time.time() - start_time:.2f}s)")

            success = True

        except subprocess.CalledProcessError as e:
            logger.error(f"Subprocess failed: {e}")
            logger.error(f"Command: {' '.join(e.cmd)}")
            logger.error(f"Stderr: {e.stderr}")
            logger.error(f"Stdout: {e.stdout}")
            success = False
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            success = False
        finally:
            # 4. Cleanup
            if temp_archive_file and os.path.exists(temp_archive_file):
                logger.debug(f"Cleaning up local temp archive: {temp_archive_file}")
                os.remove(temp_archive_file)
            if archive_on_dest_path and os.path.exists(archive_on_dest_path):
                logger.debug(f"Cleaning up destination archive: {archive_on_dest_path}")
                os.remove(archive_on_dest_path)

        if success:
            # Verify the final expected directory exists after extraction
            if os.path.isdir(final_destination_path):
                logger.info(f"Successfully copied {src_dir} to {final_destination_path}")
                return True
            else:
                logger.error(f"Extraction seems complete, but final path {final_destination_path} not found!")
                return False
        else:
            logger.error(f"Copy process failed for {src_dir} to {dst_dir}")
            return False

    def copy_directory(
        self, src_dir_path: Path, dest_dir: Path, dest_name: str = None
    ) -> Optional[Path]:
        """Copy directory to destination with optional renaming.

        Args:
            src_dir_path: Source directory to copy
            dest_dir: Destination parent directory
            dest_name: Optional new name for destination directory

        Returns:
            Path: Path to copied directory, None if error
        """
        try:
            if not src_dir_path.is_dir():
                raise NotADirectoryError(
                    f"Source directory not found: {src_dir_path}")

            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / \
                (dest_name if dest_name else src_dir_path.name)

            # Remove destination if it exists
            if dest_path.exists():
                shutil.rmtree(dest_path)

            # Copy directory recursively with metadata
            shutil.copytree(src_dir_path, dest_path)
            logger.info(
                f"Successfully copied directory {src_dir_path} to {dest_path}")
            return dest_path

        except Exception as e:
            logger.error(
                f"Error copying directory {src_dir_path} to {dest_dir}: {e}")
            return None

    def create_corpus_archive(
        self,
        corpus_dir: Path,
        corpus_archive_dir: Path,
        harness_name: str,
        round_num: int,
    ) -> Optional[Path]:
        """Create tar.gz archive of corpus files.

        Args:
            corpus_dir: Source directory containing corpus files
            corpus_archive_dir: Destination directory for archive
            harness_name: Name of the fuzzer harness
            round_num: Round number for the archive

        Returns:
            Path: Path to created archive, None if error
        """
        try:
            # Check if corpus directory exists
            if not corpus_dir.exists():
                logger.warning(f"Corpus directory not found: {corpus_dir}")
                return None

            # Create archive directory
            corpus_archive_dir.mkdir(parents=True, exist_ok=True)

            # Generate archive name
            instance_id = os.getenv("INSTANCE_ID", "default")[-6:]
            archive_name = f"{harness_name}_{instance_id}_{round_num}.tar.gz"
            archive_path = corpus_archive_dir / archive_name

            # Create tar archive with error handling for missing files
            with tarfile.open(archive_path, "w:gz") as tar:
                # Add files individually to handle missing files gracefully
                if corpus_dir.is_dir():
                    for item in corpus_dir.glob('**/*'):
                        if item.is_file():
                            try:
                                # Get relative path to maintain directory structure
                                rel_path = item.relative_to(corpus_dir.parent)
                                arcname = str(rel_path).replace(
                                    corpus_dir.name, harness_name)
                                tar.add(item, arcname=arcname)
                            except (FileNotFoundError, PermissionError) as e:
                                # Skip files that disappeared or can't be accessed
                                logger.debug(f"Skipping file {item}: {str(e)}")

            logger.info(f"Created corpus archive: {archive_path}")
            return archive_path

        except Exception as e:
            logger.error(f"Error creating corpus archive: {e}")
            logger.error(traceback.format_exc())
            return None

    def create_zip_archive(self, src_path: Path, dest_dir: Path, archive_name: str) -> Optional[Path]:
        """Create zip archive from source path.

        Args:
            src_path: Source path to zip
            dest_dir: Destination directory for zip
            archive_name: Name for zip file

        Returns:
            Path to created zip, None if error or no regular files found
        """
        try:
            # Check if there are any regular files to zip
            files_to_zip = []
            if src_path.is_file():
                if src_path.is_file():  # Ensure it's a regular file
                    files_to_zip.append((src_path, src_path.name))
            else:
                for file in src_path.rglob('*'):
                    if file.is_file():
                        rel_path = file.relative_to(src_path)
                        files_to_zip.append((file, str(rel_path)))

            # Skip writing if no regular files found
            if not files_to_zip:
                logger.info(
                    f"No regular files found under {src_path}, skipping zip creation")
                return None

            # Create destination directory
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Generate zip path
            zip_path = dest_dir / f"{archive_name}.zip"

            # Rename existing file if exists
            if zip_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = dest_dir / f"{archive_name}_{timestamp}.zip"
                zip_path.rename(backup_path)
                logger.info(f"Renamed existing archive to: {backup_path}")

            # Create zip archive
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path, arc_name in files_to_zip:
                    zf.write(file_path, arcname=arc_name)

            logger.debug(f"Created zip archive: {zip_path}")
            return zip_path

        except Exception as e:
            logger.error(f"Error creating zip archive: {e}")
            logger.error(traceback.format_exc())
            return None

    def replace_path(self, file_path: Path, old_key: str, new_key: str) -> None:
        """Replace old path with new path in file."""
        pass
