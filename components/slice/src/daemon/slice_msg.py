from dataclasses import dataclass
from typing import List, Optional

@dataclass
class SliceMsg:
    task_id: str
    is_sarif: bool
    slice_id: str
    project_name : str
    focus: str
    repo: List[str]
    fuzzing_tooling: str
    slice_target: List[List[str]]
    diff: Optional[str] = None