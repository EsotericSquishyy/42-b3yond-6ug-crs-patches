# Refbot
# Used by the filetype agent, to generate a specific file format data generation script
# The resulting script is used a a reference for Sowbot

from dataclasses import dataclass, field
from typing import Any, List, TypedDict, Annotated, Optional
import logging

from langchain_core.messages import HumanMessage, AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from seedgen2.presets import SeedGen2KnowledgeableModel, SeedGen2GenerativeModel
from seedgen2.utils.grpc import SeedD

import re


class RefbotPrompts:
    REFERENCE_REQUIREMENTS_PROMPT = """
## Requirements for the Python Script:
- Avoid importing unofficial third-party Python modules.
- Avoid usage of external tools outside of Python.
- Does not require any arguments, all generated contents should be randomly generated.
- Only generate ONE piece of content (file or packet) in a single execution of the script.
- The generated output content should be printed to stdout.

## Instructions and Steps:
- As an integrated component of an automated system, you should perform the tasks without seeking human confirmation or help.
- You MUST ensure the python code is wrapped in triple backticks for proper formatting, and it should be the only code in your response.
- You MUST include the full valid Python script in your response.
- You should wrap your script in triple backticks, like this:
```python
...
```
"""

    HANDLE_GENERATION_ERROR = """
    There is an error in your generated script according to our automated testing: {error_message}
    Please rewrite the script.
    """

    SCRIPT_NOT_FOUND = """Unable to find the generated script. You should wrap your script in triple backticks like this: ```python\n...\n```"""


@dataclass
class GenerateState(TypedDict):
    """State management for the generation workflow."""
    model: Any
    prompt: str
    messages: Annotated[list[AnyMessage], add_messages]
    error_happened: bool
    error_message: str
    error_count: int
    script: str


class ScriptExtractor:
    """Handles Python script extraction from AI responses."""

    @staticmethod
    def extract_script(content: str) -> Optional[str]:
        match = re.search(r"```python\n(.*)```", content, re.DOTALL)
        return match.group(1).strip() if match else None


class GenerationNode:
    """Handles the initial script generation."""

    def __call__(self, state: GenerateState):
        logging.info(f"Starting reference script generation for prompt: {
                     state['prompt'][:100]}...")
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
                "error_message": RefbotPrompts.SCRIPT_NOT_FOUND,
            }

        logging.info("Successfully extracted script, returning it")
        
        return {
            "error_happened": False,
            "script": script
        }


class ErrorHandlingNode:
    """Handles generation errors and requests corrections."""

    def __call__(self, state: GenerateState):
        current_error_count = state["error_count"]

        if current_error_count >= 5:
            raise Exception("Too many errors in Refbot, aborting")

        logging.info("Starting error correction iteration")
        model = state['model']
        error_prompt = RefbotPrompts.HANDLE_GENERATION_ERROR.format(
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

class Refbot:
    """Main class for generating reference script."""

    def __init__(self, seedd: SeedD, harness_binary: str, model=None):
        self.seedd = seedd
        self.harness_binary = harness_binary
        if model is None:
            self.model = SeedGen2KnowledgeableModel().model
        else:
            self.model = model

    def run(self, prompt: str) -> str:
        graph = build_generate_graph()
        full_prompt = "\n\n".join([prompt, RefbotPrompts.REFERENCE_REQUIREMENTS_PROMPT])

        initial_state = GenerateState(
            model=self.model,
            prompt=full_prompt,
            messages=[],
            error_happened=False,
            error_message="",
            error_count=0,
            script=""
        )
        result = graph.invoke(initial_state)

        return result["script"]
