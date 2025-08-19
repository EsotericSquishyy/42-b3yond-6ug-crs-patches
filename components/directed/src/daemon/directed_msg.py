from dataclasses import dataclass
from typing import List, Optional

@dataclass
class DirectedMsg:
    task_id: str
    task_type: str
    project_name : str
    focus: str
    repo: List[str]
    fuzzing_tooling: str
    diff: Optional[str] = None
    sarif_slice_path: Optional[str] = None
