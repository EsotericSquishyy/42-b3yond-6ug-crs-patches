import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import yaml

from aixcc.db import (
    Source,
    SourceTypeEnum,
    Task,
    TaskTypeEnum,
    make_session,
)
from patchagent.builder import OSSFuzzBuilder, OSSFuzzPoC, PoC
from patchagent.builder.utils import (
    BuilderProcessError,
    DockerUnavailableError,
    safe_subprocess_run,
)
from patchagent.lang import Lang
from patchagent.parser import Sanitizer, SanitizerReport, parse_sanitizer_report
from patchagent.parser.unknown import UnknownSanitizerReport

WORKSPACE = Path("/reproducer")

SANITIZER_MAP = {
    "MSAN": "memory",
    "ASAN": "address",
    "UBSAN": "undefined",
    "LSAN": "address",
    "JAZZER": "address",
    "address": "address",
    "memory": "memory",
    "undefined": "undefined",
}


class ReproBuilder(OSSFuzzBuilder):
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

    def _build_image(self, fuzz_tooling_path: Path, tries: int = 3) -> None:
        for _ in range(tries):
            process = subprocess.Popen(
                ["infra/helper.py", "build_image", "--pull", self.project],
                cwd=fuzz_tooling_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            _, stderr = process.communicate()
            if process.returncode == 0:
                return

        raise DockerUnavailableError(stderr.decode(errors="ignore"))

    def _build(self, sanitizer: Sanitizer, patch: str = "") -> None:
        if self.build_finish_indicator(sanitizer, patch).is_file():
            return

        print(f"[🧱] Building {self.project} with patch {self.hash_patch(sanitizer, patch)}")
        workspace = self.workspace / self.hash_patch(sanitizer, patch)
        source_path = workspace / self.org_source_path.name
        fuzz_tooling_path = workspace / self.org_fuzz_tooling_path.name

        shutil.rmtree(workspace, ignore_errors=True)
        shutil.copytree(self.source_path, source_path, symlinks=True)
        shutil.copytree(self.fuzz_tooling_path, fuzz_tooling_path, symlinks=True)

        safe_subprocess_run(["patch", "-p1"], source_path, input=patch.encode())

        self._build_image(fuzz_tooling_path)

        print(f"Build fuzzers source: {source_path}")
        safe_subprocess_run(
            [
                "infra/helper.py",
                "build_fuzzers",
                "--sanitizer",
                self.SANITIZER_MAP[sanitizer],
                "--clean",
                self.project,
                source_path,
            ],
            fuzz_tooling_path,
        )

        safe_subprocess_run(
            [
                "infra/helper.py",
                "check_build",
                "--sanitizer",
                self.SANITIZER_MAP[sanitizer],
                self.project,
            ],
            fuzz_tooling_path,
        )

        self.build_finish_indicator(sanitizer, patch).write_text(patch)

    def build(self, patch: str = "") -> None:
        for sanitizer in self.sanitizers:
            self._build(sanitizer, patch)

    def _replay(self, poc: PoC, sanitizer: Sanitizer, patch: str = "") -> Optional[SanitizerReport]:
        self._build(sanitizer, patch)

        assert isinstance(poc, OSSFuzzPoC), f"Invalid PoC type: {type(poc)}"
        assert poc.path.is_file(), "PoC file does not exist"
        assert self.build_finish_indicator(sanitizer, patch).is_file(), "Build failed"

        print(f"[{datetime.now()}] [🔄] (ReproBuilder) Replaying {self.project}/{poc.harness_name} with PoC {poc.path} and patch {self.hash_patch(sanitizer, patch)}")

        try:
            safe_subprocess_run(
                [
                    "infra/helper.py",
                    "reproduce",
                    self.project,
                    poc.harness_name,
                    poc.path,
                ],
                self.workspace / self.hash_patch(sanitizer, patch) / self.fuzz_tooling_path.name,
                timeout=self.replay_poc_timeout,
            )
            return None
        except BuilderProcessError as e:
            sanitizers: List[Sanitizer]
            match self.language:
                case Lang.CLIKE:
                    sanitizers = [sanitizer, Sanitizer.LibFuzzer]
                case Lang.JVM:
                    sanitizers = [sanitizer, Sanitizer.JavaNativeSanitizer, Sanitizer.LibFuzzer]

            for report in [e.stdout, e.stderr]:
                for sanitizer in sanitizers:
                    if (
                        san_report := parse_sanitizer_report(
                            report,
                            sanitizer,
                            source_path=self.source_path,
                        )
                    ) is not None:
                        return san_report

            # HACK: Check for Docker-related errors in the output
            for output_stream in [e.stdout, e.stderr]:
                if "docker: Error response from daemon:" in output_stream:
                    raise DockerUnavailableError(output_stream)

            return UnknownSanitizerReport(e.stdout, e.stderr)

    def replay(self, poc: PoC, patch: str = "") -> Optional[SanitizerReport]:
        for sanitizer in self.sanitizers:
            report = self._replay(poc, sanitizer, patch)
            if report is not None:
                return report

        return None


def download_or_decompress(url: str, path: Optional[str] = None) -> Path:
    tempfile_path = tempfile.mktemp(suffix=".tar.gz")
    if path is None:
        print(f"[📥] Downloading {url}")
        response = requests.get(url)
        response.raise_for_status()
        with open(tempfile_path, "wb") as f:
            f.write(response.content)
    else:
        print(f"[📦] Copying {path}")
        shutil.copy(path, tempfile_path)

    print(f"[📦] Decompressing {tempfile_path}")
    decompressed_path = tempfile.mkdtemp()
    shutil.unpack_archive(tempfile_path, decompressed_path)
    return Path(decompressed_path)


# Builder pool for caching builders
builder_pool: Dict[str, ReproBuilder] = {}


def create_builder(task_id: str) -> ReproBuilder:
    if task_id not in builder_pool:
        with make_session() as session:
            task = session.query(Task).filter_by(id=task_id).one()
            for source_entry in session.query(Source).filter_by(task_id=task.id, source_type=SourceTypeEnum.repo).all():
                source_path = download_or_decompress(source_entry.url, source_entry.path)
                if (source_path / task.focus).is_dir():
                    break

            fuzz_tooling_entry = session.query(Source).filter_by(task_id=task.id, source_type=SourceTypeEnum.fuzz_tooling).one()
            fuzz_tooling_path = download_or_decompress(fuzz_tooling_entry.url, fuzz_tooling_entry.path)

            diff_path = None
            if task.task_type != TaskTypeEnum.full:
                diff_entry = session.query(Source).filter_by(task_id=task.id, source_type=SourceTypeEnum.diff).one()
                diff_path = download_or_decompress(diff_entry.url, diff_entry.path)

            real_fuzz_tooling_path = None
            for subpath in fuzz_tooling_path.iterdir():
                if subpath.is_dir():
                    real_fuzz_tooling_path = fuzz_tooling_path / subpath.name
                    break

            assert real_fuzz_tooling_path is not None, "Fuzz tooling path is not a directory"
            project_yaml = real_fuzz_tooling_path / "projects" / task.project_name / "project.yaml"
            project_data = yaml.safe_load(project_yaml.read_text())

            lang: Lang = Lang.from_str(project_data["language"])

            supported_sanitizers: List[Sanitizer] = []
            for sanitizer in project_data.get("sanitizers", []):
                if sanitizer == "address":
                    match lang:
                        case Lang.CLIKE:
                            supported_sanitizers.append(Sanitizer.LeakAddressSanitizer)
                        case Lang.JVM:
                            supported_sanitizers.append(Sanitizer.JazzerSanitizer)
                elif sanitizer == "memory":
                    supported_sanitizers.append(Sanitizer.MemorySanitizer)
                elif sanitizer == "undefined":
                    supported_sanitizers.append(Sanitizer.UndefinedBehaviorSanitizer)

            if len(supported_sanitizers) == 0:
                match lang:
                    case Lang.CLIKE:
                        supported_sanitizers.append(Sanitizer.LeakAddressSanitizer)
                    case Lang.JVM:
                        supported_sanitizers.append(Sanitizer.JazzerSanitizer)

            assert len(supported_sanitizers) > 0, "No supported sanitizers found"

            builder = ReproBuilder(
                task_id,
                source_path,
                real_fuzz_tooling_path,
                task.focus,
                task.project_name,
                supported_sanitizers,
                diff_path=diff_path,
            )

            builder_pool[task_id] = builder

    return builder_pool[task_id]


def copy_poc_to_builder(pocs: List, builder: ReproBuilder) -> List:
    """
    Copy POCs to the builder workspace
    """
    workspace = builder.workspace / "pocs"

    # shutil.rmtree(workspace, ignore_errors=True)

    workspace.mkdir(parents=True, exist_ok=True)

    new_pocs = []
    pocs_uuid = str(uuid.uuid4())
    pocs_dir = workspace / pocs_uuid
    pocs_dir.mkdir(parents=True, exist_ok=True)
    for id, poc in enumerate(pocs):
        new_poc_path = pocs_dir / f"poc-{id}"
        shutil.copy(poc.path, new_poc_path)
        # Import here to avoid circular imports
        new_pocs.append(OSSFuzzPoC(new_poc_path, poc.harness_name))

    return new_pocs


def run_container(fuzz_tooling: str, project_name: str, poc_dir: Path, hash_key: str) -> None:
    image_name = "base-runner"
    image_tag = ":v1.3.0"
    container_name = f"reproducer_triage_runner_{hash_key}"

    # Check if container already exists
    check_container_cmd = ["docker", "ps", "-a", "-q", "-f", f"name={container_name}"]

    container_exists = subprocess.run(check_container_cmd, capture_output=True).stdout.decode().strip()

    parent_poc_dir = poc_dir.parent.as_posix()

    if not container_exists:
        print(f"[+] Starting container {container_name}")
        run_base_runner_cmd = [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container_name,
            "-v",
            f'{os.path.join(fuzz_tooling, "build", "out", project_name)}:/out',
            "-v",
            f"{parent_poc_dir}:/poc",
            "-t",
            f"ghcr.io/aixcc-finals/{image_name}{image_tag}",
            "sleep",
            "infinity",
        ]

        print(f"[+] Running command: {' '.join(run_base_runner_cmd)}")
        result = subprocess.run(run_base_runner_cmd, stdout=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start runner container: {result.stdout.decode()}")
        print(f"[*] Started runner container {container_name}")
    else:
        print(f"[*] Using existing runner container {container_name}")


def replay_poc(fuzz_tooling: str, project_name: str, harness_binary: str, poc_dir: Path, hash_key: str) -> Tuple[str, int]:
    container_name = f"reproducer_triage_runner_{hash_key}"
    # docker exec -it <container_name> bash -c 'TestFuzzCoreClient -runs=0 /poc'

    poc_dir_name = poc_dir.name
    exec_reproduce_cmd = ["docker", "exec", container_name, harness_binary, "-runs=0", f"/poc/{poc_dir_name}"]
    print(f"[+] Running command: {' '.join(exec_reproduce_cmd)}")
    try:
        result = subprocess.run(exec_reproduce_cmd, capture_output=True, timeout=60)
        stdout = result.stdout.decode("utf-8", errors="ignore")
        stderr = result.stderr.decode("utf-8", errors="ignore")
        returncode = result.returncode
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode("utf-8", errors="ignore") if e.stdout else ""
        stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
        returncode = 1337

    # os.remove(poc_dir)

    if "No such container" in stdout + stderr or returncode == 137:
        run_container(fuzz_tooling, project_name, poc_dir, hash_key)
        raise RuntimeError(f"Runner container not found or killed: {stdout}")

    print(f"Removing poc_dir: {poc_dir}")
    shutil.rmtree(poc_dir, ignore_errors=True)

    return stdout + stderr, returncode
