from dataclasses import dataclass
from typing import List

@dataclass
class TaskData:
    bug_id: int
    task_id: int
    task_type: str
    sanitizer: str
    harness_binary: str
    poc_path: str
    project_name: str
    focus: str
    repo: List[str]         # A list of URLs to .tar.gz files
    fuzz_tooling: str       # A URL to a .tar.gz file
    diff: str               # Another URL to a .tar.gz file