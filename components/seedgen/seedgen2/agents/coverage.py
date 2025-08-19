from seedgen2.graphs.sowbot import Sowbot, SowbotResult
from seedgen2.graphs.plainbot import Plainbot
from seedgen2.utils.grpc import SeedD
from seedgen2.presets import SeedGen2GenerativeModel, SeedGen2KnowledgeableModel
from seedgen2.graphs.sowbot import Sowbot
from seedgen2.utils.callgraph import get_current_callgraph, get_ancestors, get_successors
from seedgen2.utils.functions import FunctionInfo, locate_function
from seedgen2.utils.seeds import SeedFeedback

from typing import List
import logging

PROMPT_CHECK_COVERAGE = """
I'm giving you the source code of a fuzzing harness function, and the its uncovered region from the coverage report that I currently have for it using my set of input seeds. Please help me determine whether all important pieces of code are covered, ASIDE from unimportant codes such as failure branches from invalid inputs, error handlers, and comments.

This is the harness source code:
{source}

These are the current uncovered regions:
{uncovered_code}

Please answer with only "Yes" if you believe all codes aside from unimportant parts are covered. Otherwise answer with ONLY THE MOST IMPORTANT code regions that you believe should be covered (please include the exact lines of codes in your response), and possibly some suggestions to improve the set of input seeds to cover them.
"""

PROMPT_MAXIMIZE_COVERAGE = """
I am working on fuzzing test cases generation for a project and have developed a Python script to generate test cases for a fuzzing harness. However, I noticed that current script is not able to generate a diverse set of test cases which can achieve complete coverage of the target project.

This is the current script:
{script}

This is the source code of the harness:
{source}

These are the current uncovered important code regions, and some suggestions that can potentially increase coverage:
{uncovered_code}

The overall structure of the generated test cases from this script should still follow the structure required by the fuzzing harness code, as described in the following documentation:
{structure_documentation}

Please help me improve the script following the suggestion above to achieve coverage in the currently uncovered important code regions.
"""


def generate_based_on_coverage(
        seedd: SeedD,
        prev_result: SowbotResult,
        functions: List[FunctionInfo],
        structure_documentation: str,
        harness_binary: str,
        harness_source_code: str,
        root_function_name: str = "LLVMFuzzerTestOneInput",
        depth_limit: int = 1
) -> SowbotResult:
    seed_feedback = prev_result.seed_evaluation_result

    G = get_current_callgraph(seedd, harness_binary)

    directed_children = get_successors(G, root_function_name, depth_limit=depth_limit)
    target_function_list = [root_function_name] + directed_children

    function_source_list = []
    uncovered_list = []
    for target_function_name in target_function_list:
        target_function = next(
            (func for func in seed_feedback.partially_covered_functions if func.function_name ==
            target_function_name),
            None
        )

        if target_function is None:
            logging.info(f"The function {target_function_name} is not found or is fully covered.")
            continue
        
        target_function_loc = target_function.whole_function
        target_function_source = seedd.get_region_source(
            target_function_loc.file_path,
            target_function_loc.start_line,
            target_function_loc.start_column,
            target_function_loc.end_line,
            target_function_loc.end_column).source
        
        target_function_uncovered = [
            seedd.get_region_source(
                ur.file_path,
                ur.start_line,
                ur.start_column,
                ur.end_line,
                ur.end_column
            ).source
            for ur in target_function.uncovered_regions
        ]

        function_source_list += [f"{target_function_name}(args...){target_function_source}"]
        uncovered_list += [f"- In function {target_function_name}:\n{'\n\n'.join(target_function_uncovered)}"]

    if function_source_list == []:
        logging.info(f"All related functions are fully covered")
        return prev_result

    # model = SeedGen2KnowledgeableModel().model
    plain_model = SeedGen2GenerativeModel().model

    prompt = PROMPT_CHECK_COVERAGE.format(
        source='\n\n'.join(function_source_list),
        uncovered_code='\n\n'.join(uncovered_list)
    )

    plainbot = Plainbot(model=plain_model)
    cov_check_response = plainbot.run(prompt)

    if cov_check_response == "Yes":
        logging.info(f"All related functions are sufficiently covered according to LLM.")
        return prev_result

    sow_model = SeedGen2GenerativeModel().model
    sowbot = Sowbot(seedd, harness_binary, include_example=False, model=sow_model)

    prompt = PROMPT_MAXIMIZE_COVERAGE.format(
        script=prev_result.generator_script,
        source='\n\n'.join(function_source_list),
        uncovered_code=cov_check_response,
        structure_documentation=structure_documentation
    )

    return sowbot.run(prompt)
