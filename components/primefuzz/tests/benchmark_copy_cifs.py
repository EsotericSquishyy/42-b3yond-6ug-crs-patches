import os
import subprocess
import tempfile
import shutil
import time
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def copy_via_tar_archive(src_dir: str, dst_dir: str):
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
        logging.error(f"Source directory not found or is not a directory: {src_dir}")
        return False

    # Ensure the parent of the final destination exists
    # e.g., if copying '/tmp/data' to '/nfs/backup/', ensure '/nfs/backup/' exists.
    # The function will create '/nfs/backup/data/' based on the source basename.
    final_destination_path = os.path.join(dst_dir, os.path.basename(os.path.abspath(src_dir)))

    if not os.path.isdir(dst_dir):
         try:
            # Attempt to create the base destination directory if it doesn't exist
            os.makedirs(dst_dir, exist_ok=True)
            logging.info(f"Base destination directory created: {dst_dir}")
         except OSError as e:
            logging.error(f"Failed to create base destination directory {dst_dir}: {e}")
            return False

    # Use NamedTemporaryFile for safer handling of temp files
    temp_archive_file = None
    archive_on_dest_path = None
    success = False

    try:
        # 1. Create a temporary tar archive locally
        logging.info(f"Creating temporary archive from: {src_dir}")
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
        logging.debug(f"Executing: {' '.join(create_cmd)}")
        result = subprocess.run(create_cmd, check=True, capture_output=True, text=True)
        logging.info(f"Archive created: {temp_archive_file} (took {time.time() - start_time:.2f}s)")

        # 2. Copy the single archive file to the destination
        logging.info(f"Copying archive to destination: {dst_dir}")
        start_time = time.time()
        # Define where the archive will land on the destination side
        archive_on_dest_path = os.path.join(dst_dir, os.path.basename(temp_archive_file))
        shutil.copy2(temp_archive_file, archive_on_dest_path) # copy2 preserves metadata
        logging.info(f"Archive copied to {archive_on_dest_path} (took {time.time() - start_time:.2f}s)")

        # 3. Extract the archive in the destination directory
        logging.info(f"Extracting archive at destination: {archive_on_dest_path}")
        start_time = time.time()
        # Example: tar xf /nfs/backup/tmpxxxxxx.tar -C /nfs/backup/
        extract_cmd = ['tar', 'xf', archive_on_dest_path, '-C', dst_dir]
        logging.debug(f"Executing: {' '.join(extract_cmd)}")
        result = subprocess.run(extract_cmd, check=True, capture_output=True, text=True)
        logging.info(f"Archive extracted in {dst_dir} (took {time.time() - start_time:.2f}s)")

        success = True

    except subprocess.CalledProcessError as e:
        logging.error(f"Subprocess failed: {e}")
        logging.error(f"Command: {' '.join(e.cmd)}")
        logging.error(f"Stderr: {e.stderr}")
        logging.error(f"Stdout: {e.stdout}")
        success = False
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        success = False
    finally:
        # 4. Cleanup
        if temp_archive_file and os.path.exists(temp_archive_file):
            logging.debug(f"Cleaning up local temp archive: {temp_archive_file}")
            os.remove(temp_archive_file)
        if archive_on_dest_path and os.path.exists(archive_on_dest_path):
            logging.debug(f"Cleaning up destination archive: {archive_on_dest_path}")
            os.remove(archive_on_dest_path)

    if success:
         # Verify the final expected directory exists after extraction
        if os.path.isdir(final_destination_path):
            logging.info(f"Successfully copied {src_dir} to {final_destination_path}")
            return True
        else:
            logging.error(f"Extraction seems complete, but final path {final_destination_path} not found!")
            return False
    else:
        logging.error(f"Copy process failed for {src_dir} to {dst_dir}")
        return False


# --- Example Usage ---
if __name__ == "__main__":
    # --- Configuration ---
    # Make sure source_directory exists and has many small files
    source_directory = "/mnt/aigo/temp/code/fuzzing_target/oss-fuzz-aixcc"
    # Make sure destination_base_directory exists and is on an NFS mount
    destination_base_directory = "/crs/copy_speed_test/tmp" # e.g., /crs/shared_folder/

    # --- Create dummy source data (for testing) ---
    if not os.path.exists(source_directory):
        print(f"Creating dummy source data in {source_directory}...")
        os.makedirs(source_directory)
        for i in range(10000): # Create 10k small files
            fname = os.path.join(source_directory, f"file_{i:05d}.txt")
            with open(fname, "w") as f:
                f.write(f"This is file {i}\n" * (i % 10 + 1)) # Small content
        print("Dummy data created.")

    # --- Ensure destination base exists ---
    if not os.path.exists(destination_base_directory):
        print(f"Creating destination base directory {destination_base_directory}...")
        os.makedirs(destination_base_directory, exist_ok=True) # Make sure it exists

    # --- Run the optimized copy ---
    print("\nStarting optimized copy using tar...")
    start_total_time = time.time()
    if copy_via_tar_archive(source_directory, destination_base_directory):
        print(f"Optimized copy SUCCESS (Total time: {time.time() - start_total_time:.2f}s)")
    else:
        print(f"Optimized copy FAILED (Total time: {time.time() - start_total_time:.2f}s)")

    # --- (Optional) Run standard shutil.copytree for comparison ---
    # WARNING: This will likely be very slow on NFS with many small files!
    print("\nStarting standard shutil.copytree (expect slow)...")
    comparison_dest = os.path.join(destination_base_directory, os.path.basename(source_directory) + "_shutil")
    if os.path.exists(comparison_dest):
        print(f"Removing existing shutil comparison dir: {comparison_dest}")
        shutil.rmtree(comparison_dest) # Clean up previous run before timing
    start_shutil_time = time.time()
    try:
        shutil.copytree(source_directory, comparison_dest)
        print(f"shutil.copytree SUCCESS (Total time: {time.time() - start_shutil_time:.2f}s)")
    except Exception as e:
        print(f"shutil.copytree FAILED: {e} (Total time: {time.time() - start_shutil_time:.2f}s)")

    # --- (Optional) Clean up dummy source data ---
    print(f"\nCleaning up dummy source: {source_directory}")
    shutil.rmtree(source_directory)