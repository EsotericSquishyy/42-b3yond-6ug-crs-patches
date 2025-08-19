import logging
from langchain_core.messages import HumanMessage, AnyMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from agent.model import SeedGen2KnowledgeableModel
from typing import TypedDict, Annotated, Any


class PlainTextState(TypedDict):
    # For tracking messages
    messages: Annotated[list[AnyMessage], add_messages]

    # For storing the last response content
    response_content: str

    # Other inputs
    prompt: str
    model: Any


def NODE_prompt(state: PlainTextState):
    messages = []
    messages.append(HumanMessage(content=state['prompt']))
    response = state['model'].invoke(messages)
    messages.append(response)
    return {
        'messages': messages,
        'response_content': response.content,
    }


def build_plain_text_graph():
    graph_builder = StateGraph(PlainTextState)
    graph_builder.add_node('node_prompt', NODE_prompt)
    graph_builder.add_edge(START, 'node_prompt')
    graph_builder.add_edge('node_prompt', END)
    return graph_builder.compile()


class Plainbot:
    """
    Main class for plain text generation and validation.
    """

    def __init__(self, model=None):
        if model is None:
            self.model = SeedGen2KnowledgeableModel().model
        else:
            self.model = model

    def run(self, prompt: str) -> str:
        """
        Runs the plain text generation and validation process.
        """
        graph = build_plain_text_graph()
        initial_state = PlainTextState(
            prompt=prompt,
            model=self.model,
            messages=[],
            response_content='',
        )
        logging.info(f"Running plainbot with prompt: {prompt[:100]}...")
        result = graph.invoke(initial_state)
        logging.info(f"Plainbot finished")

        return result['response_content']
