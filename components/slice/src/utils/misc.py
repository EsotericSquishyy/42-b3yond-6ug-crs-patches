import logging
import subprocess
import tarfile
from pathlib import Path

def safe_extract_tar(tar_path, extract_path):
    """Extract tars securely"""
    extract_path = Path(extract_path).resolve()

    with tarfile.open(tar_path, "r:*") as tar:
        for member in tar.getmembers():
            member_path = (extract_path / member.name).resolve()

            if not str(member_path).startswith(str(extract_path)):
                raise RuntimeError(f"Unsafe extraction detected: {member_path}")

            tar.extract(member, extract_path)
        logging.debug(f"Safely extracted {tar_path}")

def run_command(command):
    """Run shell command"""
    try:
        result = subprocess.run(command, text=True, capture_output=True, check=True)
        logging.info(f"Command output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {e.stderr}")
        raise
