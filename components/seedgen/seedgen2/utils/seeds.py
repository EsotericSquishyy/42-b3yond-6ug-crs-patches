# Get and process dynamic information from SeedD runtime
# The dynamic information includes:
# - coverage
# - predicates
# - call graph

from dataclasses import dataclass
from typing import List
from seedgen2.utils.coverage import CoverageInfo, PartiallyCoveredFunction, parse_coverage, parse_partially_covered_functions
from seedgen2.utils.grpc import SeedD
import logging
import os


@dataclass
class SeedFeedback:
    coverage_info: CoverageInfo
    partially_covered_functions: List[PartiallyCoveredFunction]
    report: str


def run_seeds(seedd: SeedD, harness_binary: str, seed_paths: list[str]) -> SeedFeedback:
    # Seed path is a list of paths to the seed files
    # To run it with SeedD, we need to copy the seeds to the shared folder
    logging.info(f"Starting seed evaluation for {len(seed_paths)} seeds")
    shared_seed_paths = [seedd.share_file(
        seed_path) for seed_path in seed_paths]
    return __get_seed_coverage(seedd, harness_binary, shared_seed_paths)


def get_merged_coverage(seedd: SeedD, harness_binary: str) -> SeedFeedback:
    merged_coverage_result = seedd.get_merged_coverage(harness_binary)
    coverage_info = parse_coverage(merged_coverage_result.coverage)
    logging.info(f"Merged coverage results: {coverage_info}")
    partially_covered_functions = parse_partially_covered_functions(
        merged_coverage_result.coverage)
    return SeedFeedback(
        coverage_info=coverage_info,
        partially_covered_functions=partially_covered_functions,
        report=merged_coverage_result.report,
    )


def __get_seed_coverage(seedd: SeedD, harness_binary: str, seed_paths: list[str]) -> SeedFeedback:
    run_seeds_result = seedd.run_seeds(
        harness_binary=harness_binary,
        seeds_path=seed_paths,
    )
    coverage_info = parse_coverage(run_seeds_result.coverage)
    logging.info(f"Completed seed evaluation. Coverage results: {coverage_info}")
    partially_covered_functions = parse_partially_covered_functions(
        run_seeds_result.coverage)
    with open(os.path.join(seedd.shared_dir, run_seeds_result.report), "r") as f:
        report = f.read()

    return SeedFeedback(
        coverage_info=coverage_info,
        partially_covered_functions=partially_covered_functions,
        report=report,
    )
