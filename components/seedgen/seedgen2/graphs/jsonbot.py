from typing import TypedDict, Annotated, Any
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AnyMessage
import json
import jsonschema
import logging

from seedgen2.presets import SeedGen2KnowledgeableModel
from seedgen2.utils.tracker import Tracker

# Define the general state for JSON validation


class JsonValidationState(TypedDict):
    # For tracking messages
    messages: Annotated[list[AnyMessage], add_messages]

    # For tracking retries
    retries: int
    max_retries: int

    # For storing the last response content
    response_content: str

    # For error handling
    error_happened: bool
    error_message: str

    # For storing the final result
    json_result: dict

    # Other inputs
    prompt: str
    json_schema: dict
    model: Any


def NODE_initial_prompt(state: JsonValidationState):
    messages = []
    messages.append(HumanMessage(content=state['prompt']))
    response = state['model'].invoke(messages)
    messages.append(response)
    return {
        'messages': messages,
        'response_content': response.content,
        'error_happened': False,
        'error_message': '',
    }


def NODE_parse_and_validate_json(state: JsonValidationState):
    response_content = state['response_content']
    try:
        json_obj = json.loads(response_content)
        # Validate json_obj against schema
        jsonschema.validate(instance=json_obj, schema=state['json_schema'])
        # If validation succeeds
        return {
            'json_result': json_obj,
            'error_happened': False,
        }
    except Exception as e:
        return {
            'error_happened': True,
            'error_message': str(e),
        }


def NODE_check_retries(state: JsonValidationState):
    retries = state.get('retries', 0)
    retries += 1
    return {'retries': retries}


def NODE_rewrite_json(state: JsonValidationState):
    messages = state.get('messages', [])
    error_message = state['error_message']
    rewrite_prompt = f"""
There is an error in the JSON object you returned. Please rewrite the JSON object so that it conforms to the required schema.

Here is the error message:
{error_message}

Please provide only the corrected JSON object.
"""
    messages.append(HumanMessage(content=rewrite_prompt))
    response = state['model'].invoke(messages)
    messages.append(response)
    return {
        'messages': messages,
        'response_content': response.content,
    }


def EDGE_error_happened(state: JsonValidationState) -> bool:
    return state['error_happened']


def EDGE_retries_exceeded(state: JsonValidationState) -> bool:
    return state['retries'] >= state['max_retries']


def build_json_validation_graph():
    graph_builder = StateGraph(JsonValidationState)

    graph_builder.add_node('node_initial_prompt', NODE_initial_prompt)
    graph_builder.add_node('node_parse_and_validate_json',
                           NODE_parse_and_validate_json)
    graph_builder.add_node('node_check_retries', NODE_check_retries)
    graph_builder.add_node('node_rewrite_json', NODE_rewrite_json)

    graph_builder.add_edge(START, 'node_initial_prompt')

    graph_builder.add_edge('node_initial_prompt',
                           'node_parse_and_validate_json')

    graph_builder.add_conditional_edges(
        'node_parse_and_validate_json',
        EDGE_error_happened,
        {
            False: END,
            True: 'node_check_retries',
        }
    )

    graph_builder.add_conditional_edges(
        'node_check_retries',
        EDGE_retries_exceeded,
        {
            True: END,
            False: 'node_rewrite_json',
        }
    )

    graph_builder.add_edge('node_rewrite_json', 'node_parse_and_validate_json')

    return graph_builder.compile()


class Jsonbot:
    """Main class for JSON generation and validation."""

    def __init__(self, max_retries: int = 3, model=None):
        self.max_retries = max_retries
        if model is None:
            self.model = SeedGen2KnowledgeableModel().json_model
        else:
            self.model = model

    def run(self, prompt: str, json_schema: dict) -> dict:
        """
        Runs the JSON generation and validation process.

        Args:
            prompt: The input prompt for generation
            json_schema: The JSON schema to validate against

        Returns:
            dict: The validated JSON result
        """
        graph = build_json_validation_graph()
        initial_state = JsonValidationState(
            prompt=prompt,
            json_schema=json_schema,
            model=self.model,
            max_retries=self.max_retries,
            retries=0,
            messages=[],
            response_content='',
            error_happened=False,
            error_message='',
            json_result={},
        )
        logging.info(f"Running jsonbot with prompt: {prompt[:100]}...")

        result = graph.invoke(initial_state)

        logging.info(f"Jsonbot finished")

        tracker = Tracker()
        tracker.add_trace(
            prompt=prompt,
            result=result['json_result'],
            bot_name="jsonbot",
            additional_info={
                "retries": result['retries'],
            },
        )

        return result['json_result']
