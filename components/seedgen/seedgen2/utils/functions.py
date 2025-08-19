# Get function information from SeedD runtime

from dataclasses import dataclass
from typing import List, Optional
import json

from seedgen2.utils.grpc import SeedD


@dataclass
class FunctionInfo:
    name: str
    file_path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int


def parse_functions(json_str: str) -> List[FunctionInfo]:
    response = json.loads(json_str)
    return [FunctionInfo(**fi) for fi in response]


def get_functions(seedd: SeedD, harness_binary: str) -> List[FunctionInfo]:
    get_function_result = seedd.get_functions(harness_binary).functions
    return parse_functions(get_function_result)


def locate_function(function: str, functions: List[FunctionInfo]) -> Optional[FunctionInfo]:
    # TODO: handle multiple functions with the same name in C++
    return next((f for f in functions if f.name == function), None)
