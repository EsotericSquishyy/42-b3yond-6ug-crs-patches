# Seed Generator wiht MCP adaptors
# Only relies on the harness source code, without SeedD and getcov
import asyncio
from pathlib import Path

from seedgen2.agents.alignment import align_script, update_doc_mini
from seedgen2.agents.filetype import generate_based_on_filetype, get_filetype, generate_reference_script
from seedgen2.agents.glance import generate_first_script, initial_code_analysis
from seedgen2.utils.generators import SeedGeneratorStore
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
from typing import Any, List, Callable, Optional

from seedgen2.presets import SeedGen2GenerativeModel

import logging
import json

from seedgen2.utils.tracker import Tracker
import re
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


class MCPAnalysisResponse(BaseModel):
    data_format_doc: str = Field(
        description="docs on how to compose the data structure, like expected input format")
    plan: str = Field(description="Code plan from the analysis")


class CodeAnalysisAgent:
    """Agent responsible for code analysis and planner.
    Note: Use a separate agent for code analysis as the code base consumes too many tokens.
    """

    def __init__(self, harness_source: str, project_path: str, diff_dir: Optional[str] = None):
        self.client = MultiServerMCPClient(
            {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", str(Path(project_path).parent)],
                    "transport": "stdio",
                },
                "treesitter": {
                    "command": "python3",
                    "args": ["-m", "mcp_server_tree_sitter.server", "--config", "treesitter_config.yaml"],
                    "transport": "stdio",
                    "env": {
                        "MCP_TS_LOG_LEVEL": "WARNING",
                    }
                }
            }
        )
        self.agent = None
        # NOTE: update to List if we need to perform parallel analysis on multiple harnesses sources.
        self.harness_source = harness_source
        self.project_path = project_path
        self.diff_dir = diff_dir if diff_dir else None
        self.analysis_result = {}

    def extract_json_result(self, resp_text: str) -> dict:
        """Extract JSON result between ```json and ``` from the raw text with regex."""
        try:
            pattern = r"```json\s*([\s\S]*?)\s*```"
            match = re.search(pattern, resp_text)
            if match:
                json_str = match.group(1)
                return json.loads(json_str)
            else:
                logging.warning("No JSON block found in the response text")
                return {}
        except (ValueError, json.JSONDecodeError) as e:
            logging.error(f"Failed to extract JSON: {e}")
            return {}

    async def setup_analysis_agent_react(self, model_name: str = "gpt-4o") -> Any:
        """Set up the react agent."""
        tools = await self.client.get_tools()
        # logging.debug(f"MCP Tools: {tools}")
        self.agent = create_react_agent(
            model_name, tools, response_format=MCPAnalysisResponse)

    async def setup_analysis_agent_stateful(self, model_name: str = "gpt-4o") -> Any:
        """Set up LangGraph StateGraph."""
        # builder = StateGraph(MessagesState)
        # builder.add_node(call_model)
        # builder.add_node(ToolNode(tools))
        # builder.add_edge(START, "call_model")
        # builder.add_conditional_edges(
        #     "call_model",
        #     tools_condition,
        # )
        # builder.add_edge("tools", "call_model")
        # graph = builder.compile()
        # self.agent = ?
        # TODO: complete later
        pass

    async def run_analysis(self, user_msg=None) -> dict:
        """Run the analysis.
        Returns:
            dict: Analysis result
        """
        result = {}
        if self.agent:
            user_message = user_msg or "Project Path:{project_path}\n\nHarness code:{harness_code}\n".format(
                harness_code=self.harness_source,
                project_path=self.project_path
            )
            mcp_response = await self.agent.ainvoke({"messages": user_message}, {"recursion_limit": 30})
            if mcp_response:
                structured_response = mcp_response["structured_response"]
                logging.debug(f"Analysis response: {structured_response}")
                result = {"structure": structured_response.data_format_doc,
                          "plan": structured_response.plan}
            else:
                logging.error("No response from MCP agent.")

        self.analysis_result = result
        logging.info(f"Analysis result: {self.analysis_result}")

    def wait_for_analysis(self, model_name: str = "gpt-4o", usr_msg=None, callback: Optional[Callable[[Any], None]] = None) -> None:
        """Wait for the analysis to complete."""
        try:
            logging.info("Waiting for MCP analysis to complete...")
            asyncio.run(self.setup_analysis_agent_react(model_name))
            logging.info("Running analysis...")
            asyncio.run(self.run_analysis(usr_msg))

            if self.agent and callback:
                callback(self.analysis_result)

        except RuntimeError as e:
            if " asyncio.run() cannot be called from a running event loop" in str(e):
                logging.error(f"Error: {e}")
                print("This typically means you're trying to call asyncio.run() "
                      "from within an already running async environment (e.g., inside another "
                      "async function, or a framework that manages its own loop like Jupyter/IPython "
                      "with autoawait). Consider restructuring or using nest_asyncio if appropriate.")
            else:
                # Re-raise other RuntimeErrors
                raise

        logging.info("MCP analysis completed successfully.")


class SeedMcpAgent:
    """Agent responsible for generating seeds based on various strategies."""

    def __init__(self, result_dir: str, src_dir: str, project_name: str, harness_binary: str, harness_source: str, gen_model: str, diff_dir: Optional[str] = None):
        """Initialize the SeedGenAgent.

        Args:
            result_dir: Directory to store results
            project_name: Name of the project
            harness_binary: Path to the harness binary
            harness_source: Source code of the harness binary
        """
        self.shared_dir = Path(f"{result_dir}/../shared")
        self.result_dir = Path(result_dir)
        self.src_dir = Path(src_dir)
        self.diff_dir = Path(diff_dir) if diff_dir else None
        self.project_name = project_name
        self.harness_binary = harness_binary
        self.harness_source = harness_source
        self.store = SeedGeneratorStore()
        self.store.set_result_dir(result_dir)
        self.tracker = Tracker()
        self.tracker.set_log_dir(result_dir)
        SeedGen2GenerativeModel.set_custom_model(gen_model)

    def run(self) -> None:
        """Run the seed generation process."""
        logging.info(f"Running SeedGen2 MCP agent for harness binary: {
                     self.harness_binary}")

        # Seed generation pipeline
        # 1. Analyze the source code first to get suggestions on data structures and code plans
        code_analysis_result = initial_code_analysis(
            CodeAnalysisAgent(self.harness_source,
                              str(self.src_dir.absolute())),
            self.harness_source,
            self.harness_binary,
            str(self.src_dir.absolute()),
            str(self.diff_dir.absolute()) if self.diff_dir else None,
        )

        # 2. Generate 3 ingredients: initial generator script, structure documentation, and target filetype
        current_result = generate_first_script(
            None, self.harness_source, self.harness_binary, additional_context=code_analysis_result)
        current_script = current_result.generator_script
        current_doc = update_doc_mini(self.harness_source, self.harness_binary)
        filetype_result = get_filetype(
            harness_source_code=self.harness_source,
            harness_file_name=self.harness_binary,
            project_name=self.project_name,
        )
        filetype_result = filetype_result.translate(
            str.maketrans('', '', "\"'`"))  # remove quotes and ticks

        # 3. Generate the complete generator script
        if filetype_result == "unknown":
            logging.info(
                f"Unknown filetype, only using structure information for generation")
            current_result = align_script(
                None, current_script, current_doc, self.harness_binary)
        else:
            logging.info(f"Generating seeds for filetype {filetype_result}")
            reference_script = generate_reference_script(
                None, self.harness_binary, filetype_result)
            current_result = generate_based_on_filetype(
                None,
                current_script,
                current_doc,
                self.harness_binary,
                self.harness_source,
                filetype_result,
                True,
                reference_script
            )
