from dataclasses import dataclass, field
from typing import Any, List, TypedDict, Annotated, Optional
import logging
import subprocess
import sys
import os
import json

from langchain_core.messages import HumanMessage, AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from seedgen2.presets import SeedGen2GenerativeModel
from seedgen2.utils.grpc import SeedD
from seedgen2.utils.generators import GeneratorRunResult, SeedGeneratorStore
from seedgen2.utils.seeds import SeedFeedback, run_seeds
from seedgen2.utils.tracker import Tracker

import re

from dotenv import load_dotenv
import os

load_dotenv()


class CodexbotPrompts:
    ULTRA_THINKING_PROMPT = """
Ultra-deep thinking mode. Greater rigor, attention to detail, and multi-angle verification. Start by outlining the task and breaking down the problem into subtasks. For each subtask, explore multiple perspectives, even those that seem initially irrelevant or improbable. Purposefully attempt to disprove or challenge your own assumptions at every step. Triple-verify everything. Critically review each step, scrutinize your logic, assumptions, and conclusions, explicitly calling out uncertainties and alternative viewpoints.  Independently verify your reasoning using alternative methodologies or tools, cross-checking every fact, inference, and conclusion against external data, calculation, or authoritative sources. Deliberately seek out and employ at least twice as many verification tools or methods as you typically would. Use mathematical validations, web searches, logic evaluation frameworks, and additional resources explicitly and liberally to cross-verify your claims. Even if you feel entirely confident in your solution, explicitly dedicate additional time and effort to systematically search for weaknesses, logical gaps, hidden assumptions, or oversights. Clearly document these potential pitfalls and how you've addressed them. Once you're fully convinced your analysis is robust and complete, deliberately pause and force yourself to reconsider the entire reasoning chain one final time from scratch. Explicitly detail this last reflective step.

<task>
{task}
</task>
"""

    REQUIREMENTS_PROMPT = """
## Requirements for the Python Script:
- Avoid importing unofficial third-party Python modules.
- Has one argument, which is the output file path.
- Generate one test case and write it to the output file.
- The generated test case should be compatible with the fuzzing harness code provided.

## Instructions and Steps:
- As an integrated component of an automated system, you should perform the tasks without seeking human confirmation or help.
- You MUST ensure the python code is wrapped in triple backticks for proper formatting, and it should be the only code in your response.
- You MUST include the full valid Python script in your response.
- You should wrap your script in triple backticks, like this:
```python
...
```
"""

    ONE_SHOT_EXAMPLE = """
Here is an example of Python script used to generate a testcase file. You can use this as a reference to create your own script:

```python
#!/usr/bin/env python3

import sys
import random
import base64
from typing import BinaryIO

def generate_input(rng: BinaryIO, out: BinaryIO, original_data: bytes):
    # original_data: constants data for your reference
    # random_num = rng.read(1)[0] % 100 + 1
    # generated_data = ?
    out.write(generated_data)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate.py <output_file_path>")
        sys.exit(1)
    
    # replace it with constants that may be useful to the fuzzer
    original_data = b"0000"

    with open('/dev/urandom', 'rb') as rng, open(sys.argv[1], 'wb') as out:
        generate_input(rng, out, original_data)
```
"""

    HANDLE_GENERATION_ERROR = """
    There is an error in your generated script according to our automated testing: {error_message}
    Please rewrite the script.
    """

    SCRIPT_NOT_FOUND = """Unable to find the generated script. You should wrap your script in triple backticks like this: ```python\n...\n```"""

    @staticmethod
    def get_full_prompt(prompt: str, context: str, include_requirements: bool = True, include_example: bool = True) -> str:
        """Builds the full prompt with optional requirements and example."""
        components = [prompt]
        if include_requirements:
            components.append(CodexbotPrompts.REQUIREMENTS_PROMPT)
        if include_example:
            components.append(CodexbotPrompts.ONE_SHOT_EXAMPLE)
        components.append(context)
        return CodexbotPrompts.ULTRA_THINKING_PROMPT.format(task="\n".join(components))


def codex_invoke(prompt, target_project_dir, model):
    try:
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = os.getenv("LITELLM_KEY")
        env["OPENAI_BASE_URL"] = os.getenv("LITELLM_BASE_URL")

        result = subprocess.run(
            ['codex', '-q', '--approval-mode', 'full-auto',
                '--model', model, f'"{prompt}"'],
            text=True,
            capture_output=True,
            check=True,
            env=env,
            cwd=target_project_dir
        )

        responses = result.stdout.splitlines()
        return json.loads(responses[-1])["content"][0]["text"]

    except subprocess.CalledProcessError as e:
        print("Error running LLM command:", e, file=sys.stderr)
        raise


@dataclass
class GenerateState(TypedDict):
    """State management for the generation workflow."""
    model: Any
    prompt: str
    target_project_dir: str
    messages: Annotated[list[AnyMessage], add_messages]
    error_happened: bool
    error_count: int
    error_message: str
    generated_script_id: int
    generator_run_result: Optional[GeneratorRunResult]


class ScriptExtractor:
    """Handles Python script extraction from AI responses."""

    @staticmethod
    def extract_script(content: str) -> Optional[str]:
        match = re.search(r"```python\n(.*)```", content, re.DOTALL)
        return match.group(1).strip() if match else None


class GenerationNode:
    """Handles the initial script generation."""

    def __call__(self, state: GenerateState):
        logging.info(f"Starting script generation for prompt: {
                     state['prompt'][:100]}...")
        prompt = state['prompt']
        target_project_dir = state["target_project_dir"]
        model = state['model']
        messages = [HumanMessage(content=state["prompt"])]
        response = codex_invoke(prompt, target_project_dir, model)

        return {"messages": messages + [response]}


class ScriptValidationNode:
    """Validates and runs the generated script."""

    def __call__(self, state: GenerateState):
        last_response = state["messages"][-1].content
        if isinstance(last_response, list):
            last_response = "\n".join([str(item) for item in last_response])
        script = ScriptExtractor.extract_script(last_response)

        if not script:
            logging.error("Failed to extract script from model response")
            return {
                "error_happened": True,
                "error_message": CodexbotPrompts.SCRIPT_NOT_FOUND,
            }

        logging.info(
            "Successfully extracted script, starting generator execution")
        store = SeedGeneratorStore(num_seeds=400)
        generator_id = store.new_generator(script)
        run_result = store.run_generator(generator_id)

        if not run_result.is_success():
            logging.error(f"Failed to run generator: {
                          run_result.get_error_message()}")
            return {
                "error_happened": True,
                "error_message": f"Failed to run generator: {run_result.get_error_message()}",
            }

        logging.info("Successfully ran generator script")
        return {
            "error_happened": False,
            "generated_script_id": generator_id,
            "generator_run_result": run_result,
        }


class ErrorHandlingNode:
    """Handles generation errors and requests corrections."""

    def __call__(self, state: GenerateState):
        current_error_count = state["error_count"]

        if current_error_count >= 5:
            raise Exception("Too many errors in Codexbot, aborting")

        logging.info("Starting error correction iteration")
        target_project_dir = state["target_project_dir"]
        model = state['model']
        error_prompt = CodexbotPrompts.HANDLE_GENERATION_ERROR.format(
            error_message=state["error_message"])
        messages = [HumanMessage(content=error_prompt)]
        response = codex_invoke(
            state["messages"] + messages, target_project_dir, model)

        return {"messages": messages + [response], "error_count": current_error_count + 1}


def EDGE_error_happened(state: GenerateState) -> bool:
    return state["error_happened"]


def build_generate_graph():
    """Builds the generation workflow graph."""
    graph_builder = StateGraph(GenerateState)

    # Add nodes
    graph_builder.add_node("generate", GenerationNode())
    graph_builder.add_node("validate_script", ScriptValidationNode())
    graph_builder.add_node("handle_error", ErrorHandlingNode())

    # Configure edges
    graph_builder.add_edge(START, "generate")
    graph_builder.add_edge("generate", "validate_script")
    graph_builder.add_conditional_edges(
        "validate_script",
        EDGE_error_happened,
        {True: "handle_error", False: END}
    )
    graph_builder.add_edge("handle_error", "validate_script")

    return graph_builder.compile()


@dataclass
class CodexbotResult:
    """Results from a Codexbot generation run."""
    generator_script: str
    seeds: List[str]
    seed_evaluation_result: SeedFeedback


class Codexbot:
    """Main class for generating and evaluating seeds."""

    def __init__(self, seedd: SeedD, harness_binary: str, target_project_dir: str, enforce_requirements: bool = True, include_example: bool = True, model=None):
        self.seedd = seedd
        self.harness_binary = harness_binary
        self.target_project_dir = target_project_dir
        self.enforce_requirements = enforce_requirements
        self.include_example = include_example
        if model is None:
            self.model = SeedGen2GenerativeModel().model
        else:
            self.model = model

    def run(self, prompt: str, context: str) -> CodexbotResult:
        """
        Runs the seed generation and evaluation process.

        Args:
            prompt: The input prompt for generation

        Returns:
            CodexbotResult containing generated scripts and evaluation results
        """
        graph = build_generate_graph()
        full_prompt = CodexbotPrompts.get_full_prompt(
            prompt,
            context,
            include_requirements=self.enforce_requirements,
            include_example=self.include_example
        )

        initial_state = GenerateState(
            model=self.model,
            prompt=full_prompt,
            target_project_dir=self.target_project_dir,
            messages=[],
            error_happened=False,
            error_count=0,
            error_message="",
            generated_script_id=0,
            generator_run_result=None,
        )
        result = graph.invoke(initial_state)

        generator_id = result["generated_script_id"]
        generator_run_result = result["generator_run_result"]

        store = SeedGeneratorStore()
        seeds = generator_run_result.get_seed_paths()
        generator_script = store.get_generator(generator_id)
        if self.seedd:
            seed_feedback = run_seeds(self.seedd, self.harness_binary, seeds)
        else:
            # Empty SeedD means Seedgen is running in mini mode
            # So we don't run and evaluate seeds at all
            seed_feedback = SeedFeedback(
                coverage_info=None,
                partially_covered_functions=None,
                report=None,
            )

        tracker = Tracker()
        tracker.add_trace(
            prompt=full_prompt,
            result=generator_script,
            bot_name="Codexbot",
            additional_info={
                "generator_id": generator_id,
                "coverage": seed_feedback.coverage_info,
                "report": seed_feedback.report,  # Export report for better evaluation
            }
        )

        return CodexbotResult(
            generator_script=generator_script,
            seeds=seeds,
            seed_evaluation_result=seed_feedback,
        )
