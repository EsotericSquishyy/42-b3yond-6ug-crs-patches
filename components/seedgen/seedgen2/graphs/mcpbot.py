from typing import Any, List, TypedDict, Annotated, Optional
from dataclasses import dataclass
from langchain_core.messages import HumanMessage, AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from seedgen2.presets import SeedGen2GenerativeModel
from seedgen2.utils.grpc import SeedD
from seedgen2.utils.generators import GeneratorRunResult, SeedGeneratorStore
from seedgen2.utils.seeds import SeedFeedback, run_seeds
from seedgen2.utils.tracker import Tracker
import logging
import re


class McpPrompts:
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

    CODE_ANALYSIS_PROMPT = """
**Objective:** Analyze the provided fuzzing harness code and its interaction with the associated codebase to understand the structure of the test cases it expects. The ultimate aim is to gather information critical for effective fuzzing.

**Inputs Provided:**
*   The fuzzing harness code.
*   (Optionally) The codebase the harness interacts with.

**Analysis Guidelines & Tasks:**

1.  **Identify Entry Point:**
    *   For C/C++ code, assume the entry point is `LLVMFuzzerTestOneInput`.
    *   For Java (JVM) code, assume the entry point is `fuzzerTestOneInput`.

2.  **AST-based Analysis (Conditional Requirement):**
    *   If Abstract Syntax Tree (AST) analysis is deemed necessary for a comprehensive understanding of the input structure or control flow (e.g., to trace complex data dependencies or specific parsing logic), the relevant code/project must be registered with Treesitter (tools provided) prior to such analysis.*
    * use register_project_tools to register the project with Treesitter at first.
    * avoid using get_ast because it will consume too many tokens.
    * pay more attention to the code that contains the string like "aixcc" and "jazzer".
    * backdoor may be inserted in the code, so potential backdoor keywords should be noticed.

3.  **Harness Interaction & Input Structure Deconstruction:**
    *   Analyze how the harness code processes its input data.
    *   Determine how the harness code interacts with the main codebase (if provided).
    *   Detail the expected structure of a valid test case input. Pay close attention to and document the following:
        *   **Constant Strings and Numbers:** Identify any literal strings or numerical values that are part of the expected input format or that are used in parsing/validation logic within the harness.
        *   **Headers or Metadata Fields:** Describe any identifiable header sections or metadata fields. For each, specify its name, expected format, potential values, size, and its role in the input processing.
        *   **Specific Data Fields:** For each distinct data field the harness expects, document:
            *   Its **location** within the input stream/structure.
            *   Its **data type** (e.g., integer (signed/unsigned, bit width), string (null-terminated, length-prefixed), float, boolean, custom struct).
            *   Any **encoding method** used (e.g., ASCII, UTF-8, Base64, hex, custom serialization).
            *   Known **constraints**, expected ranges, or specific patterns.
        *   **Control Flow Dependencies (Fuzzing Dictionary Candidates):** Identify specific strings, numbers, magic values, or patterns within the input that directly influence control flow decisions within the harness or the called functions (e.g., values used in `switch` statements, `if/else if` conditions, or as command identifiers). These are crucial for building effective fuzzing dictionaries.

**Expected Output from Me:**
*   A detailed description of the expected input
*   A coding plan on how to write a Python script for the test case generator.

**Expected Output Format:**
*  The output should be in a JSON object.
*  The JSON object should contain the following keys:
    - data_format_doc: A detailed description of the expected input structure.
    - plan: A coding plan on how to write a Python script for the test case generator.
* an example of the expected JSON output:
    {{"data_format_doc": string ...docs on how to compose the data structure, plan: string...1. create a list of ...; 2. create a fucntion to ...}}

"""

    BASIC_PROMPT = """
## Inputs:
1.  **Harness Code:** 
{harness_code}
2.  **Target Project Path:** {target_project_path}
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
            components.append(McpPrompts.REQUIREMENTS_PROMPT)
        if include_example:
            components.append(McpPrompts.ONE_SHOT_EXAMPLE)
        components.append(context)
        return "\n".join(components)

    @staticmethod
    def get_pre_analysis_prompt(prompt: str, context: str) -> str:
        """Builds the full prompt with optional requirements and example."""
        components = [prompt]
        components.append(context)
        components.append(McpPrompts.CODE_ANALYSIS_PROMPT)
        return "\n".join(components)


@dataclass
class GenerateState(TypedDict):
    """State management for the generation workflow."""
    model: Any
    prompt: str
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
        logging.info(f"Starting script generation for prompt: {state['prompt'][:100]}...")
        model = state['model']
        messages = [HumanMessage(content=state["prompt"])]
        response = model.invoke(messages)

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
                "error_message": McpPrompts.SCRIPT_NOT_FOUND,
            }

        logging.info(
            "Successfully extracted script, starting generator execution")
        store = SeedGeneratorStore()
        generator_id = store.new_generator(script)
        run_result = store.run_generator(generator_id)

        if not run_result.is_success():
            logging.error(f"Failed to run generator: {run_result.get_error_message()}")
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
            raise Exception("Too many errors in mcpbot, aborting")

        logging.info("Starting error correction iteration")
        model = state['model']
        error_prompt = McpPrompts.HANDLE_GENERATION_ERROR.format(
            error_message=state["error_message"])
        messages = [HumanMessage(content=error_prompt)]
        response = model.invoke(state["messages"] + messages)

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
class McpbotResult:
    """Results from a MCPbot generation run."""
    generator_script: str
    seeds: List[str]
    seed_evaluation_result: SeedFeedback
