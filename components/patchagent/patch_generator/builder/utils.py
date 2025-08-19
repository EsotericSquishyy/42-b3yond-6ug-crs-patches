import shutil
import tempfile
from pathlib import Path
from typing import Optional

import requests

from patch_generator.logger import logger


def download_or_decompress(url: str, path: Optional[str] = None) -> Path:
    tempfile_path = tempfile.mktemp(suffix=".tar.gz")

    if path is None:
        logger.info(f"[📥] Downloading {url}")
        response = requests.get(url)
        response.raise_for_status()
        with open(tempfile_path, "wb") as f:
            f.write(response.content)
    else:
        logger.info(f"[📦] Copying {path}")
        shutil.copy(path, tempfile_path)

    logger.info(f"[📦] Decompressing {tempfile_path}")
    decompressed_path = tempfile.mkdtemp()
    shutil.unpack_archive(tempfile_path, decompressed_path)
    return Path(decompressed_path)
