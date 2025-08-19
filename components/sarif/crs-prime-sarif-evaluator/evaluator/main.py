"""
This script demonstrates how to use the MCP Agent to analyze SARIF files and source code.
It uses the MCP framework to create an agent that can interact with various tools and LLMs.
TODO: reachability check for a sarif file on multiple fuzzers
"""
import asyncio
import os
import argparse
import time
import json

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
# from mcp_agent.workflows.llm.augmented_llm_google import GoogleAugmentedLLM
from .prompts import EVALUATOR_SYSTEM_PROMPT, SUMMARY_USER_PROMPT
from .uitls import process_result

# from .telemetry import init_opentelemetry

app = MCPApp(name="mcp_basic_agent")


async def run_sarif_eval(sarif_path: str, target_src_path: str, workspace: str, crash_path: str | None = None, preliminary: bool = False, result_path: str | None = None, model: str = "openai"):
    async with app.run() as agent_app:
        logger = agent_app.logger
        context = agent_app.context

        sarif_agent = Agent(
            name="sarif_validator",
            instruction=EVALUATOR_SYSTEM_PROMPT,
            server_names=["filesystem", "treesitter"],
        )

        context.config.mcp.servers["filesystem"].args.extend(
            [workspace])

        if os.getenv("OPENAI_API_KEY"):
            context.config.openai.api_key = os.getenv("OPENAI_API_KEY")
        if os.getenv("OPENAI_MODEL"):
            context.config.openai.default_model = os.getenv("OPENAI_MODEL")
        if os.getenv("ANTHROPIC_API_KEY"):
            context.config.anthropic.api_key = os.getenv("ANTHROPIC_API_KEY")
        if os.getenv("ANTHROPIC_MODEL"):
            context.config.anthropic.default_model = os.getenv("ANTHROPIC_MODEL")
        if os.getenv("ANTHROPIC_API_BASE"):
            context.config.anthropic.base_url = os.getenv("ANTHROPIC_API_BASE")
        if os.getenv("OPENAI_API_BASE"):
            context.config.openai.base_url = os.getenv("OPENAI_API_BASE")

        async with sarif_agent:
            logger.info(
                "SARIF Agent: Connected to server, calling list_tools...")
            result = await sarif_agent.list_tools()
            logger.info("Tools available:", data=result.model_dump())

            # Select LLM based on model parameter
            if model.lower() == "anthropic":
                llm = await sarif_agent.attach_llm(AnthropicAugmentedLLM)
            else:  # default to OpenAI
                llm = await sarif_agent.attach_llm(OpenAIAugmentedLLM)

            message = f"Perform analysis based on SARIF file(s) {sarif_path}, the source code path is {target_src_path}. {"There is a crash report file " + crash_path + " that may be related to the SARIF file. If you believe this SARIF file is correct but is not related to this crash, please treat it as incorrect" if crash_path is not None else ""}. {"I would like to reduce false negatives in this analysis, so you should only claim it as an incorrect SARIF if you are confident enough." if preliminary else ""}"
            logger.info(f"Sending to LLM...: {message}")
            result = await llm.generate_str(
                message=message
            )
            logger.info(f"Analysis Result: {result}")

            # Multi-turn conversations
            result = await llm.generate_str(
                message=SUMMARY_USER_PROMPT
            )
            logger.info(f"JSON Result: {result}")

            if result_path:
                try:
                    with open(result_path, 'w') as f:
                        result_json = process_result(result)
                        json.dump(result_json, f, indent=4)

                    logger.info(f"Saved JSON result to {result_path}")
                except Exception as e:
                    logger.error(
                        f"Failed to save result to {result_path}: {e}")


def main_cli():
    # Create argument parser
    parser = argparse.ArgumentParser(description="Run SARIF analysis agent.")
    parser.add_argument(
        "sarif_path", help="Path to the SARIF file or a path contains SARIF files.")
    parser.add_argument("target_src_path",
                        help="Path to the target source code directory.")
    parser.add_argument("--result_path",
                        help="Optional path to save the JSON result.", default=None)
    parser.add_argument("--model",
                        help="LLM model to use: 'openai' or 'anthropic'",
                        choices=["openai", "anthropic"],
                        default="openai")
    parser.add_argument(
        "--crash_path", help="Path to the crash file.", default=None)
    parser.add_argument(
        "--preliminary", help="Whether it is a preliminary check.", action="store_true", default=False)
    parser.add_argument(
        "--workspace", help="Path to the workspace.", required=True)

    # Parse arguments
    args = parser.parse_args()

    start = time.time()
    
    
    # Initialize OpenTelemetry
    # init_opentelemetry(
    #     otel_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"),
    #     otel_headers=os.getenv("OTEL_EXPORTER_OTLP_HEADERS", ""),
    #     otel_protocol=os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc"),
    #     service_name="mcp_sarif_evaluator"
    # )
    
    # Pass parsed arguments to the function
    asyncio.run(run_sarif_eval(sarif_path=args.sarif_path,
                target_src_path=args.target_src_path,
                workspace=args.workspace,
                result_path=args.result_path,
                model=args.model,
                crash_path=args.crash_path,
                preliminary=args.preliminary,
                ))
    end = time.time()
    t = end - start

    print(f"Total run time: {t:.2f}s")


if __name__ == "__main__":
    main_cli()
