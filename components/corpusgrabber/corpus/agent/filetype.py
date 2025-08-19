import hashlib
import os
from agent.plainbot import Plainbot
from agent.model import SeedGen2KnowledgeableModel

PROMPT_determine_file_type = """
Help me determine if there is a common file type (or protocol) that is being used as part of a test case for this fuzzing harness. In other words, based on the source code of the harness, you need to determine any potential common file type (or protocol) that is being used.

You should return only the name of the file type (or protocol) in your response, and nothing else, e.g. `jpg`, `png`, `gif`, etc. or `http`, `tcp`, etc. If the file type (or protocal) has multiple common names, such as `jpg` and `jpeg`, please return the shortest version of it. If the file type (or protocol) is not determined (or not a commonly known one), you should return `unknown`.

For conext:
The project under test's name is {project_name}.
This is the source code of the harness:
```
{harness_source_code}
```
"""

def log_prompt(prompt, result, log_dir):
    trace_file_path = os.path.join(
        log_dir, f"trace_{hashlib.md5(prompt.encode('utf-8')).hexdigest()}.txt")

    with open(trace_file_path, "w") as f:
        f.write("# PROMPT:\n")
        f.write(f"calling filetype with prompt:\n")
        f.write(f"```\n{prompt}\n```\n\n")
        f.write("\n\n# RESULT:\n")
        f.write(f"```\n{result}\n```\n\n")
        f.write("\n")


def get_filetype(
        harness_source_code: str,
        project_name: str,
        log_dir: str
) -> str:
    # Build the prompt
    prompt = PROMPT_determine_file_type.format(
        harness_source_code=harness_source_code,
        project_name=project_name
    )

    knowledgeable_model = SeedGen2KnowledgeableModel().model

    plainbot = Plainbot(model=knowledgeable_model)
    result = plainbot.run(prompt)

    log_prompt(prompt, result, log_dir)

    return result

