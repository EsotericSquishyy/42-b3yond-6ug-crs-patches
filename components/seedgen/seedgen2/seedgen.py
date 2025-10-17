# Seed Generator 2
# Author: Wenxuan Shi <wenxuan.shi@northwestern.edu>
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

from seedgen2.agents.alignment import align_script, update_doc
from seedgen2.agents.filetype import generate_based_on_filetype, get_filetype, generate_reference_script
from seedgen2.agents.coverage import generate_based_on_coverage
from seedgen2.agents.glance import generate_first_script
from seedgen2.graphs.sowbot import SowbotResult
from seedgen2.utils.grpc import SeedD
from seedgen2.utils.generators import SeedGeneratorStore
from seedgen2.utils.functions import get_functions, FunctionInfo

from seedgen2.presets import SeedGen2GenerativeModel

import logging
import os

from seedgen2.utils.seeds import get_merged_coverage
from seedgen2.utils.tracker import Tracker
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


@dataclass
class HarnessInfo:
    """Contains information about the harness file."""
    file_path: str
    source_code: str
    file_name: str


class SeedGenAgent:
    """Agent responsible for generating seeds based on various strategies."""

    def __init__(self, result_dir: str, ip_addr: str, project_name: str, harness_binary: str, gen_model: str):
        """Initialize the SeedGenAgent.

        Args:
            result_dir: Directory to store results
            ip_addr: IP address for SeedD service
            project_name: Name of the project
            harness_binary: Path to the harness binary
        """
        self.seedd = SeedD(ip_addr, shared_dir=f"{result_dir}/../shared")
        self.result_dir = Path(result_dir)
        self.project_name = project_name
        self.harness_binary = harness_binary
        self.store = SeedGeneratorStore()
        self.store.set_result_dir(result_dir)
        self.tracker = Tracker()
        self.tracker.set_log_dir(result_dir)
        SeedGen2GenerativeModel.set_custom_model(gen_model)


    def _find_harness_function(self, functions: List[FunctionInfo]) -> Optional[FunctionInfo]:
        return next(
            (func for func in functions if "LLVMFuzzerTestOneInput" in func.name),
            None
        )

    def _get_harness_info(self, functions: List[FunctionInfo]) -> HarnessInfo:
        harness_func = self._find_harness_function(functions)
        if not harness_func:
            raise ValueError(
                "Failed to locate the harness file. No function named 'LLVMFuzzerTestOneInput' found."
            )

        logging.info(f"Located harness file: {harness_func.file_path}")

        source_code = self.seedd.get_region_source(
            filepath=harness_func.file_path,
            start_line=0, start_column=0,
            end_line=0, end_column=0
        ).source

        return HarnessInfo(
            file_path=harness_func.file_path,
            source_code=source_code,
            file_name=Path(harness_func.file_path).name
        )

    def _generate_filetype_seeds(self, prev_result: SowbotResult, structure_documentation: str, harness_info: HarnessInfo) -> SowbotResult:
        filetype_result = get_filetype(
            harness_source_code=harness_info.source_code,
            harness_file_name=harness_info.file_name,
            project_name=self.project_name,
        )

        filetype_result = filetype_result.translate(str.maketrans('', '', "\"'`")) # remove quotes and ticks

        logging.info(f"Identified file type: {filetype_result}")

        if filetype_result == "unknown":
            logging.info(f"Unknown filetype, skipping script regeneration")
            return prev_result

        reference_script = generate_reference_script(self.seedd, self.harness_binary, filetype_result)

        return generate_based_on_filetype(
            self.seedd,
            prev_result.generator_script,
            structure_documentation,
            self.harness_binary,
            harness_info.source_code,
            filetype_result,
            True,
            reference_script
        )

    def run(self) -> None:
        """Run the seed generation process."""
        logging.info(f"Running SeedGen2 agent for harness binary: {self.harness_binary}")

        # Get functions and harness information
        functions = get_functions(self.seedd, self.harness_binary)
        harness_info = self._get_harness_info(functions)

        # Seed generation pipeline

        # 1. Generate an initial script and an initial test case structure documentation
        current_result = generate_first_script(
            self.seedd, harness_info.source_code, self.harness_binary)
        current_script = current_result.generator_script
        current_doc = update_doc(
            self.seedd, current_result.seed_evaluation_result, functions, self.harness_binary)
        
        # Experiment with doing filetype first
        current_result = self._generate_filetype_seeds(
            current_result, current_doc, harness_info)
        
        # Alignment once afterwards
        current_doc = update_doc(
            self.seedd, current_result.seed_evaluation_result, functions, self.harness_binary, current_doc)
        
        current_result = align_script(
                self.seedd, current_result.generator_script, current_doc, self.harness_binary)

        # Finally, evaluate the coverage
        merged_coverage_report = get_merged_coverage(self.seedd, self.harness_binary)
        with open(os.path.join(self.seedd.shared_dir, merged_coverage_report.report), "r") as f:
            report = f.read()
        with open(os.path.join(self.result_dir, "merged_coverage.txt"), "w") as f:
            f.write(str(merged_coverage_report.coverage_info))
            f.write(str(report))
