# Glance subgraph of SeedGen2

# 1. Generating the first round of a seed generation script, based purely on the source code of a fuzzing harness
# 2. Generating the subsequent rounds of the script, based on previous scripts and seed format documentation

import os
from seedgen2.presets import SeedGen2InferModel, SeedGen2ContextModel
from seedgen2.graphs.sowbot import Sowbot
from seedgen2.graphs.mcpbot import McpPrompts
from seedgen2.utils.grpc import SeedD

PROMPT_GENERATE_FIRST_SCRIPT = """
Given the source code of a fuzzing harness, analyze the harness and generate a Python script that can be used to generate valid testcases for the given harness. Try your best to ensure the generated testcases cover as much harness code as possible. The generated test cases should be diverse and effective for security testing purposes. Consider various input types, edge cases, and potential vulnerabilities relevant to the system being tested. Ensure your script can produce a wide range of test scenarios to thoroughly exercise the target application or protocol.
"""

CONTEXT_GENERATE_FIRST_SCRIPT = """
## For context:
Here is the source code of the harness:
{harness_source_code}
"""

PROMPT_MCP_INITIAL_CODE_ANALYSIS = """
Performance the code analysis on the source code and the fuzzing harness according to the following instructions.
The goal is to provide a high-level overview of the code structure, key components, and any potential areas of interest for further exploration. 
"""

CONTEXT_CODEBASE_ANALYSIS = """
The source code of target project is under the directory: {src_path}.
"""

CONTEXT_DIFF_ANALYSIS = """
The diff file is located at: {diff_path} . (default file name is ref.diff )
the content of the diff file is as follows:
{diff_file_content}
This diff file contains the changes made to the source code, which may introduce new bugs. Analyze the diff to understand how to prepare seeds that can trigger more bugs.
"""


def generate_first_script(
        seedd: SeedD,
        harness_source_code: str,
        harness_binary: str,
        additional_context: dict = None
):
    model = SeedGen2InferModel().model
    prompt = PROMPT_GENERATE_FIRST_SCRIPT
    context = CONTEXT_GENERATE_FIRST_SCRIPT.format(
        harness_source_code=harness_source_code
    )

    if additional_context:
        context += "\nData format:\n{structure_doc}".format(
            structure_doc=additional_context.get('structure', '')
        )

        context += "\nCode Plan:\n{code_plan}".format(
            code_plan=additional_context.get('plan', '')
        )

    sowbot = Sowbot(seedd, harness_binary, model=model)

    return sowbot.run(prompt, context)


def initial_code_analysis(
        mcpagent: object,
        harness_source_code: str,
        harness_binary: str,
        src_path: str,
        diff_path: str = None
):
    model = SeedGen2ContextModel().model
    result = {}
    def func_test_callback(x): return result.update(x)

    # code context
    context = CONTEXT_GENERATE_FIRST_SCRIPT.format(
        harness_source_code=harness_source_code
    ) + CONTEXT_CODEBASE_ANALYSIS.format(
        src_path=src_path
    )
    if diff_path:
        print("[DEBUG] Using diff path for analysis:", diff_path)
        try:
            with open(os.path.join(diff_path, "ref.diff"), 'r') as diff_file:
                diff_content = diff_file.read()
        except FileNotFoundError:
            print(
                "[DEBUG] diff file not found, AI will find at its own discretion", diff_path)
            diff_content = ""

        context = context + CONTEXT_DIFF_ANALYSIS.format(
            diff_path=diff_path,
            diff_file_content=diff_content,
        )
    final_prompt = McpPrompts.get_pre_analysis_prompt(
        prompt=PROMPT_MCP_INITIAL_CODE_ANALYSIS, context=context)
    if hasattr(mcpagent, "run_analysis"):
        mcpagent.wait_for_analysis(
            model_name=model, usr_msg=final_prompt, callback=func_test_callback)
    else:
        print("[DEBUG] mcpagent does not have run_analysis method")

    # print("[DEBUG ONLY] Code analysis result:", result)
    return result
