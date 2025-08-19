from dataclasses import dataclass
from typing import List

@dataclass
class TaskData:
    task_id: int
    task_type: str
    project_name: str
    focus: str
    repo: List[str]         # A list of URLs to .tar.gz files
    fuzz_tooling: str       # A URL to a .tar.gz file
    diff: str               # Another URL to a .tar.gz file
