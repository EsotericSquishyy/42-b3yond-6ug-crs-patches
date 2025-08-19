import os
import subprocess
import sys
import json

from dotenv import load_dotenv

load_dotenv()

ULTRA_THINKING_PROMPT = """
Ultra-deep thinking mode. Greater rigor, attention to detail, and multi-angle verification. Start by outlining the task and breaking down the problem into subtasks. For each subtask, explore multiple perspectives, even those that seem initially irrelevant or improbable. Purposefully attempt to disprove or challenge your own assumptions at every step. Triple-verify everything. Critically review each step, scrutinize your logic, assumptions, and conclusions, explicitly calling out uncertainties and alternative viewpoints.  Independently verify your reasoning using alternative methodologies or tools, cross-checking every fact, inference, and conclusion against external data, calculation, or authoritative sources. Deliberately seek out and employ at least twice as many verification tools or methods as you typically would. Use mathematical validations, web searches, logic evaluation frameworks, and additional resources explicitly and liberally to cross-verify your claims. Even if you feel entirely confident in your solution, explicitly dedicate additional time and effort to systematically search for weaknesses, logical gaps, hidden assumptions, or oversights. Clearly document these potential pitfalls and how you've addressed them. Once you're fully convinced your analysis is robust and complete, deliberately pause and force yourself to reconsider the entire reasoning chain one final time from scratch. Explicitly detail this last reflective step.

<task>
{task}
</task>
"""


def log_convo(convo, log_dir):
    os.makedirs(log_dir, exist_ok=True)

    with open(os.path.join(log_dir, "logs.json"), "w") as f:
        f.write(convo)


def codex_dedup(
    project_name,
    target_project_dir,
    crash_bases, crash_new,
    model="o4-mini",
    log_dir=None
):
    """
    Check if a new crash is a duplicate of any crash in the base list.

    Args:
        project_name: Name of the project
        target_project_dir: Directory of the project
        crash_bases: List of base crash reports to compare against
        crash_new: New crash report to check
        model: Model to use for analysis

    Returns:
        bool: True if the new crash is a duplicate of any base crash, False otherwise
    """

    # Format all base crashes into a single string
    base_crashes_text = ""
    for i, crash_base in enumerate(crash_bases):
        base_crashes_text += f"Base crash #{i+1}:\n{crash_base}\n\n"

    prompt = (
        f"You are an expert software engineer, specialized in crash triaging. You are given one or multiple base crash report(s) and a new crash report for the project {project_name} and its codebase, the current directory corresponds to /src in the crash reports:\n\n"
        f"{base_crashes_text}"
        f"New crash report to analyze:\n{crash_new}\n\n"
        f"This is what you need to do:\n"
        "1. Analyze in-depth to understand the EXACT LOCATION IN CODE THAT IS THE ROOT CAUSE of all these crash reports, using the code analysis tools available to you to understand the functions that were called in the stack traces.\n"
        "2. Answer this question, responding with ONLY 'YES' or 'NO': Is the new crash report triggered by the same root cause as ALL of the base crash reports? IMPORTANT: Be conservative with your answer. Only answer 'YES' if you are 100-percent sure and can pinpoint the exact location in code that is the common root cause of all the crashes.\n"
        "You MUST follow these rules:\n"
        "- Do your own investigation autonomously. End the conversation after completing all tasks and do not ask for more information.\n"
        "- The stack traces in the crash reports might contain many functions. DO NOT skip over any of them, try to understand the crash with an in-depth analysis. REMEMBER: It's the EXACT ROOT CAUSE that matters, not the crash location or the type of crash.\n"
        "- Don't forget to register the project to treesitter first, if you want to use it.\n"
        "- Don't EVER try to read more tokens than a message can handle at once from a source file.\n"
    )

    # Run the LLM command with a timeout
    try:
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = os.getenv("LITELLM_KEY")
        env["OPENAI_BASE_URL"] = os.getenv("LITELLM_BASE_URL")

        if os.getenv("ULTRA_THINKING_MODE", False):
            full_prompt = f'"{ULTRA_THINKING_PROMPT.format(task=prompt)}"'
        else:
            full_prompt = f'"{prompt}"'

        result = subprocess.run(
            ['codex', '-q', '--approval-mode', 'full-auto',
                '--model', model, full_prompt],
            text=True,
            capture_output=True,
            check=True,
            env=env,
            cwd=target_project_dir
        )

        responses = result.stdout.splitlines()
        final_response = json.loads(responses[-1])["content"][0]["text"]
        if log_dir:
            log_convo(result.stdout, log_dir)
        if "YES" in final_response:
            return True
        return False

    except subprocess.CalledProcessError as e:
        print("Error running Codex Dedup command:", e, file=sys.stderr)
        return False
