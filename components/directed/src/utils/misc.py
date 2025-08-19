import logging
import subprocess
import tarfile
from pathlib import Path
import hashlib
import os
import time

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


def generate_random_sha256() -> str:
    """
    Generate a random SHA256 hash in hexadecimal format.

    Returns:
        A 64-character hexadecimal string representing a SHA256 hash.
    """
    # Generate 32 random bytes
    random_data = os.urandom(32)
    # Compute SHA256 hash of the random data
    hash_obj = hashlib.sha256(random_data)
    # Return the hexadecimal representation of the hash
    return hash_obj.hexdigest()

def get_file_sha256(file_path):
    """
    Return the SHA256 hash of a file.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def wait_for_path(path: Path, timeout: int = 30, interval: float = 1.0):
    logging.info(f"Waiting for path {path} to exist...")
    for _ in range(timeout):
        if path.exists():
            return
        time.sleep(interval)
    raise FileNotFoundError(f"Output directory {path} does not exist.")
