# Use langgraph to build a COT "model".
# This model is supposed to be transparent for upper layers,
# it receives a HumanMessage and returns an AIMessage.

from dataclasses import dataclass
from typing import Any, List, Optional, Annotated, TypedDict
import json
import logging
import operator

from langchain_core.messages import HumanMessage, AIMessage, AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from seedgen2.presets import SeedGen2GenerativeModel


class CoTPrompts:
    PROMPT_COT = """
You are an expert AI assistant that explains your reasoning step by step. For each step, provide a title that describes what you're doing in that step, along with the content. Decide if you need another step or if you're ready to give the final answer. Respond in JSON format with 'title', 'content', and 'next_action' (either 'continue' or 'final_answer') keys. USE AS MANY REASONING STEPS AS POSSIBLE. AT LEAST 3. BE AWARE OF YOUR LIMITATIONS AS AN LLM AND WHAT YOU CAN AND CANNOT DO. IN YOUR REASONING, INCLUDE EXPLORATION OF ALTERNATIVE ANSWERS. CONSIDER YOU MAY BE WRONG, AND IF YOU ARE WRONG IN YOUR REASONING, WHERE IT WOULD BE. FULLY TEST ALL OTHER POSSIBILITIES. YOU CAN BE WRONG. WHEN YOU SAY YOU ARE RE-EXAMINING, ACTUALLY RE-EXAMINE, AND USE ANOTHER APPROACH TO DO SO. DO NOT JUST SAY YOU ARE RE-EXAMINING. USE AT LEAST 3 METHODS TO DERIVE THE ANSWER. USE BEST PRACTICES.

Example of a valid JSON response:
```json
{
    "title": "Identifying Key Information",
    "content": "To begin solving this problem, we need to carefully examine the given information and identify the crucial elements that will guide our solution process. This involves...",
    "next_action": "continue"
}```
"""

    FINAL_PROMPT = "Please provide the final answer based solely on your reasoning above. Do not use JSON formatting. Only provide the text response without any titles or preambles. Retain any formatting as instructed by the original prompt, such as exact formatting for free response or multiple choice."


class COTState(TypedDict):
    """State management for Chain-of-Thought reasoning."""
    model: Any
    json_model: Any
    messages: Annotated[List[AnyMessage], add_messages]
    error_happened: bool
    error_message: str
    step_count: int
    max_steps: int
    final_answer: Optional[str]
    next_action: str
    chain_of_thought: Annotated[List[str], operator.add]


class GenerateStepNode:
    """Generates a reasoning step."""

    def __call__(self, state: COTState):
        logging.info(f"Generating reasoning step {state['step_count'] + 1}")
        model = state["json_model"]
        messages = state["messages"]

        # Generate the next reasoning step
        response = model.invoke(messages)
        step_count = state["step_count"] + 1

        # Parse the assistant's response
        try:
            step_data = json.loads(response.content)
            next_action = step_data.get("next_action", "final_answer")
            logging.info(f"STEP {step_count}. {step_data.get('title'):<20}: {step_data.get('content')}")
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON response: {e}")
            return {
                "error_happened": True,
                "error_message": f"Failed to parse JSON response: {e}",
                "next_action": "final_answer"
            }

        return {
            "step_count": step_count,
            "messages": [response],
            "next_action": next_action,
            "chain_of_thought": [
                f"{step_data.get('title')}: {step_data.get('content')}"
            ]
        }


class GenerateFinalAnswerNode:
    """Generates the final answer."""

    def __call__(self, state: COTState):
        logging.info("Generating final answer")
        model = state["model"]
        # Ask the assistant to provide the final answer

        prompt = CoTPrompts.FINAL_PROMPT

        messages = state["messages"] + [HumanMessage(content=prompt)]

        response = model.invoke(messages)

        return {
            "final_answer": response.content,
            "messages": [prompt, response],
        }


def EDGE_should_continue(state: COTState) -> bool:
    return state["next_action"] != 'final_answer' and state["step_count"] < state["max_steps"]


def build_cot_graph():
    """Builds the Chain-of-Thought reasoning graph."""
    graph_builder = StateGraph(COTState)

    # Add nodes
    graph_builder.add_node("generate_step", GenerateStepNode())
    graph_builder.add_node("generate_final_answer", GenerateFinalAnswerNode())

    # Configure edges
    graph_builder.add_edge(START, "generate_step")
    graph_builder.add_conditional_edges(
        "generate_step",
        EDGE_should_continue,
        {True: "generate_step", False: "generate_final_answer"}
    )
    graph_builder.add_edge("generate_final_answer", END)

    return graph_builder.compile()


class CoT:
    """Main class for Chain-of-Thought reasoning."""

    def __init__(self, model=None, json_model=None):
        if model is None:
            self.model = SeedGen2GenerativeModel().model
            self.json_model = SeedGen2GenerativeModel().json_model
        else:
            if json_model is None:
                raise ValueError("json_model is required if model is provided")
            self.model = model
            self.json_model = json_model

        self.chain_of_thought = []

    def invoke(self, messages: List[AnyMessage]) -> AIMessage:
        """
        Runs the chain-of-thought reasoning process.

        Args:
            messages: The input messages for reasoning.

        Returns:
            The final answer generated by the model.
        """
        graph = build_cot_graph()

        initial_state = COTState(
            model=self.model,
            json_model=self.json_model,
            messages=[
                HumanMessage(content=CoTPrompts.PROMPT_COT),
                *messages,
                AIMessage(
                    content="Thank you! I will now think step by step following my instructions, starting at the beginning after decomposing the problem."
                )
            ],
            error_happened=False,
            error_message='',
            final_answer=None,
            step_count=0,
            max_steps=25,
            next_action="continue",
            chain_of_thought=[]
        )

        result = graph.invoke(initial_state)
        if result.get("final_answer") is None:
            raise ValueError("No final answer generated")

        self.chain_of_thought = result.get("chain_of_thought", [])
        return AIMessage(content=result["final_answer"])

    def get_chain_of_thought(self) -> List[str]:
        """
        A secret API that returns the chain-of-thought reasoning steps from last invocation.
        """
        return self.chain_of_thought
