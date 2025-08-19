# Seed Generator 2 with Codex
# Only relies on the harness source code and code base, without SeedD and getcov
from pathlib import Path

from seedgen2.graphs.codexbot import Codexbot
from seedgen2.utils.generators import SeedGeneratorStore

import logging
import os

from seedgen2.utils.tracker import Tracker
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


class SeedCodexAgent:
    """Agent responsible for generating seeds based on various strategies."""

    def __init__(self, result_dir: str, project_name: str, harness_binary: str, harness_source: str, target_project_dir: str, model: str):
        """Initialize the SeedGenAgent.

        Args:
            result_dir: Directory to store results
            project_name: Name of the project
            harness_binary: Path to the harness binary
            harness_source: Source code of the harness binary
        """
        self.shared_dir = Path(f"{result_dir}/../shared")
        self.result_dir = Path(result_dir)
        self.project_name = project_name
        self.harness_binary = harness_binary
        self.harness_source = harness_source
        self.target_project_dir = target_project_dir
        self.store = SeedGeneratorStore()
        self.store.set_result_dir(result_dir)
        self.tracker = Tracker()
        self.tracker.set_log_dir(result_dir)
        self.model = model

    def run(self) -> None:
        """Run the seed generation process."""
        logging.info(f"Running SeedGen2 Codex agent for harness binary: {
                     self.harness_binary}")

        # Seed generation pipeline
        prompt = (
            f"You are an expert software engineer, specialized in code analysis. You are given the source code of a fuzzing harness called {self.harness_binary} for the project {self.project_name} and its codebase. This is the harness source code:\n"
            f"{self.harness_source}\n"
            f"This is what you need to do:\n"
            "1. Analyze this harness and how it interacts with the codebase. Try to understand the structure of a test case that the harness expects, including, but not limited to:\n"
            "- Headers or metadata fields and their characteristics.\n"
            "- Specific data fields: location, type, encoding method, etc.\n"
            "- Emphasize usage of common file types' contents within the test structure: their location, fields, specific requirements, etc.\n"
            "- Other specific requirements.\n"
            "2. Generate a Python script that can be used to generate valid testcases for the given harness. Try your best to ensure the generated testcases cover as much of the harness code and the code base as possible. The generated test cases should be diverse and effective for security testing purposes. Consider various input types, edge cases, and potential vulnerabilities relevant to the system being tested. Ensure your script can produce a wide range of test scenarios to thoroughly exercise the target application or protocol.\n"
            "You MUST follow these rules:\n"
            "- Do your own investigation autonomously. End the conversation after completing all tasks and do not ask for more information.\n"
            "- Don't forget to register the project to treesitter first, if you want to use it.\n"
            "- Don't EVER try to read more tokens than a message can handle at once from a source file.\n"
        )

        codexbot = Codexbot(None, self.harness_binary,
                            self.target_project_dir, model=self.model)

        codexbot.run(prompt, "")
