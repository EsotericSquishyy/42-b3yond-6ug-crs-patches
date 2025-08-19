import json
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PartiallyCoveredPredicate:
    file_path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    true_count: int
    false_count: int


@dataclass
class CodeRegion:
    file_path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int  # Exclusive


@dataclass
class PartiallyCoveredFunction:
    function_name: str
    file_path: str
    partially_covered_predicates: List[PartiallyCoveredPredicate]
    uncovered_regions: List[CodeRegion]
    whole_function: Optional[CodeRegion]


@dataclass
class CoverageInfo:
    covered_branches: int
    total_branches: int
    covered_functions: int
    total_functions: int


def parse_coverage(json_str: str) -> CoverageInfo:
    response = json.loads(json_str)
    coverage = response['coverage']

    return CoverageInfo(
        covered_branches=coverage['covered_branches'],
        total_branches=coverage['total_branches'],
        covered_functions=coverage['covered_functions'],
        total_functions=coverage['total_functions'],
    )


def parse_partially_covered_functions(json_str: str) -> List[PartiallyCoveredFunction]:
    """Parses a JSON representation of PartiallyCoveredFunction into a Python object."""
    response = json.loads(json_str)
    uncovered_functions = response['uncovered_functions']

    def parse_predicate(d: dict) -> PartiallyCoveredPredicate:
        return PartiallyCoveredPredicate(
            file_path=d['file_path'],
            start_line=d['start_line'],
            start_column=d['start_column'],
            end_line=d['end_line'],
            end_column=d['end_column'],
            true_count=d['true_count'],
            false_count=d['false_count'],
        )

    def parse_code_region(d: dict) -> CodeRegion:
        return CodeRegion(
            file_path=d['file_path'],
            start_line=d['start_line'],
            start_column=d['start_column'],
            end_line=d['end_line'],
            end_column=d['end_column'],
        )

    # for each function, parse the predicates and uncovered regions
    partially_covered_functions = []
    for func in uncovered_functions:
        partially_covered_predicates = [
            parse_predicate(p) for p in func.get('partially_covered_predicates', [])
        ]

        uncovered_regions = [
            parse_code_region(r) for r in func.get('uncovered_regions', [])
        ]

        whole_function = (
            parse_code_region(func['whole_function'])
            if func.get('whole_function')
            else None
        )

        partially_covered_functions.append(
            PartiallyCoveredFunction(
                function_name=func['function_name'],
                file_path=func['file_path'],
                partially_covered_predicates=partially_covered_predicates,
                uncovered_regions=uncovered_regions,
                whole_function=whole_function,
            )
        )

    return partially_covered_functions
