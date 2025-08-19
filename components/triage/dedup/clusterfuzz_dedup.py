import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from clusterfuzz._internal.crash_analysis.crash_result import CrashResult
from clusterfuzz._internal.crash_analysis.crash_comparer import CrashComparer

# The pattern we use to yank "Instrumented ..." lines. One sample line:
# INFO: Instrumented org.apache.commons.compress.archivers.ArchiveInputStream (took 9 ms, size +9%)
# Our regex will yank only
# org.apache.commons.compress.archivers.ArchiveInputStream
# INSTRUMENTATION_PATTERN = re.compile(pattern=r".*Instrumented\s(?P<fragment>.*)\s\(.*")
INSTRUMENTATION_PATTERN = re.compile(
    pattern=r"Instrumented\s(?P<fragment>[A-Za-z0-9\.]*)\s"
)

_this_directory = os.path.dirname(os.path.realpath(__file__))


def instrumentation_key_from_fuzz_artefact(fuzz_artefact: str) -> str | None:
    """
    Given a fuzz artefact, create a key that can be used to identify it by its
    instrumentation pattern
    """
    matches = INSTRUMENTATION_PATTERN.findall(fuzz_artefact)
    return "\n".join(sorted(matches)) if matches else None


def crash_state_from_fuzz_artefact(
    fuzz_artefact: str,
    return_code: int | None = None,
    crash_time: datetime | None = None,
    unexpected_crash: bool = False,
    custom_stack_frame_ignore_regexes: list[str] | None = None,
) -> str:
    """
    Given an output fuzz artefact ( actual log output from running a fuzzer ), generate
    the clusterfuzz 'crash state' for that fuzz output.
    You may include return_code, crash_time, and whether the crash was unexpected.
    If the project you're targeting has stack_frame_ignore_regexes defined in its
    project.yaml file, you should include them as a list of strings.
    """

    # NOTE / JANK
    # project.yaml is so deeply embedded into clusterfuzz that it's wildly difficult to
    # ignore. In this particular case, it would appear that the only reason why we're
    # using it at all is to fetch stack from ignore regexes for the project that we're
    # looking at. Because it's not likely that we'll be able to decouple this setup in
    # code that isn't ours, we just heavily monkey-patch clusterfuzz's code instead,
    # substituting our own reality.
    # This puts the onus on the caller to know which ( if any ) regexes are defined for
    # the targeted project.
    # The final mock -- ...local_config.ProjectConfig.get -- is the most meaningful one,
    # and allows us to substitute our input list.

    custom_stack_frame_ignore_regexes = custom_stack_frame_ignore_regexes or []
    with (
        patch(
            "clusterfuzz._internal.system.environment.get_config_directory"
        ) as mock_get_config_directory,
        patch(
            "clusterfuzz._internal.config.local_config._validate_root"
        ) as mock_validate_root,
        patch(
            "clusterfuzz._internal.config.local_config.ProjectConfig.get"
        ) as mock_get_config,
    ):
        mock_get_config.return_value = custom_stack_frame_ignore_regexes
        mock_get_config_directory.return_value = _this_directory
        mock_validate_root.return_value = True

        crash_state = CrashResult(
            return_code=return_code or 0,
            crash_time=crash_time,
            output=fuzz_artefact,
            unexpected_crash=unexpected_crash,
        ).get_state()

        return crash_state if crash_state != "NULL" else None


def clusterfuzz_dedup(crash_bases, crash_new, threshold=0.8):
    dupe_count = 0
    for crash_base in crash_bases:
        crash_state_base = crash_state_from_fuzz_artefact(crash_base)
        crash_state_new = crash_state_from_fuzz_artefact(crash_new)

        instrumentation_key_base = instrumentation_key_from_fuzz_artefact(
            crash_base)
        instrumentation_key_new = instrumentation_key_from_fuzz_artefact(
            crash_new)

        crash_state_comparer = CrashComparer(crash_state_base, crash_state_new)
        instrumentation_key_comparer = CrashComparer(
            instrumentation_key_base, instrumentation_key_new)

        if crash_state_comparer.is_similar() or instrumentation_key_comparer.is_similar():
            dupe_count += 1

    return dupe_count / len(crash_bases) >= threshold
