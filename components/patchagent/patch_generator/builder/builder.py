import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from patch_generator.env import WORKSPACE
from patchagent.builder import OSSFuzzBuilder
from patchagent.parser.sanitizer import Sanitizer


class AIXCCBuilder(OSSFuzzBuilder):
    def __init__(
        self,
        id: str,
        source_path: Path,
        fuzz_tooling_path: Path,
        focus: str,
        project: str,
        sanitizers: List[Sanitizer],
        diff_path: Optional[Path] = None,
    ):

        real_source_path = source_path / focus

        if diff_path is None:
            super().__init__(project, real_source_path, fuzz_tooling_path, sanitizers, WORKSPACE / id)
        else:
            pre_workspace = WORKSPACE / f"pre-{id}"
            shutil.copytree(real_source_path, pre_workspace / focus)

            for diff in diff_path.rglob("*.diff"):
                subprocess.run(
                    ["patch", "-p1"],
                    cwd=pre_workspace / focus,
                    input=diff.read_bytes(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                break

            super().__init__(project, pre_workspace / focus, fuzz_tooling_path, sanitizers, WORKSPACE / id)
