# Filetype subgraph of SeedGen2
# filetype stage is to improve the seed generation script, using information about common file types

from seedgen2.graphs.plainbot import Plainbot
from seedgen2.graphs.sowbot import Sowbot, SowbotResult
from seedgen2.graphs.refbot import Refbot
from seedgen2.utils.grpc import SeedD

from seedgen2.presets import SeedGen2KnowledgeableModel, SeedGen2GenerativeModel

PROMPT_determine_file_type = """
Help me determine if there is a common file type (or protocol) that is being used as part of a test case for this fuzzing harness. In other words, based on the source code of the harness, you need to determine any potential common file type (or protocol) that is being used.

You should return only the name of the file type (or protocol) in your response, and nothing else, e.g. `jpg`, `png`, `gif`, etc. or `http`, `tcp`, etc. If the file type (or protocol) is not determined (or not a commonly known one), you should return `unknown`.

For conext:
The project under test's name is {project_name}.
This is the source code of the harness `{harness_file_name}`:
```
{harness_source_code}
```
"""

PROMPT_reference = """
Help me write me a python script that can generate random files (or packets) for the {file_type} file type (or protocol). Please make sure it that the generator script can generate a diverse set of {file_type} files or packets and cover all different features that the file format or protocol offers.
"""

PROMPT_generate = """
I am working on a fuzzing project and have developed a Python script to generate test cases for a fuzzing harness. However, I noticed that the test harness might make use of a specific common file type (or network packet) called {file_type}. Currently, the test case generation script only generates a small limited amount of {file_type} content, in a hard-coded manner. Therefore, I need your help to improve the script to encompass a more diverse and structural generation of this file type (or protocol packet)'s content as part of the test case generation, in order to increase the overall test coverage.

After the improvement, with the addition of generating {file_type} content, the overall structure of the generated test cases from this script should still follow the structure required by the fuzzing harness code, as described in the following documentation given below.
"""

CONTEXT_generate = """
## For context:
This is the current python script:
{script}

This is test case structure documentation that I mentioned:
{structure_documentation}
"""

CONTEXT_file_generator_script = """
Furthermore, you can use the following script as a reference on how to generate random contents for the {file_type} file type or packet, which could generate data that cover the intricacies of the structures and features of the file format or protocol:
{script}
"""

def get_filetype(
        harness_source_code: str,
        harness_file_name: str,
        project_name: str
) -> str:
    # Build the prompt
    prompt = PROMPT_determine_file_type.format(
        harness_source_code=harness_source_code,
        harness_file_name=harness_file_name,
        project_name=project_name
    )

    knowledgeable_model = SeedGen2KnowledgeableModel().model

    plainbot = Plainbot(model=knowledgeable_model)
    return plainbot.run(prompt)

def generate_reference_script(
        seedd: SeedD,
        harness_binary: str,
        filetype_info: str
) -> str:
    prompt = PROMPT_reference.format(
        file_type=filetype_info
    )

    model = SeedGen2GenerativeModel().model

    refbot = Refbot(seedd, harness_binary, model=model)
    return refbot.run(prompt)


def generate_based_on_filetype(
        seedd: SeedD,
        script: str,
        structure_documentation: str,
        harness_binary: str,
        harness_source_code: str,
        filetype_info: str,
        include_reference: bool = False,
        reference_script: str = ""
) -> SowbotResult:
    model = SeedGen2GenerativeModel().model
    sowbot = Sowbot(seedd, harness_binary, include_example=False, model=model)

    prompt = PROMPT_generate.format(
        file_type=filetype_info,
    )
    context = CONTEXT_generate.format(
        script=script,
        structure_documentation=structure_documentation
    )

    if include_reference:
        context += CONTEXT_file_generator_script.format(
            file_type=filetype_info,
            script=reference_script
        )
        
    return sowbot.run(prompt, context)
