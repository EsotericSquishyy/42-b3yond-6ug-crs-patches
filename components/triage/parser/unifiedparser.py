import re
import hashlib
from typing import List, Optional, Tuple, Dict, Any, Union
from enum import StrEnum
from pathlib import Path
import logging

from parser.sanitizer import Sanitizer, SanitizerReport

# Combined regex patterns that work for all sanitizer types
SANITIZER_NAME_PATTERN = r"(?:AddressSanitizer|MemorySanitizer|UndefinedBehaviorSanitizer|ThreadSanitizer|LeakSanitizer|libFuzzer)"

# Pattern for traditional format with process ID
TRADITIONAL_PATTERN = fr"((?:==[0-9]+==)?\s*(?:ERROR|WARNING): ({SANITIZER_NAME_PATTERN})(?:: .*)?)SUMMARY: ({SANITIZER_NAME_PATTERN})"
TRADITIONAL_HEADER_PATTERN = fr"(?:==[0-9]+==)?\s*(?:ERROR|WARNING): ({SANITIZER_NAME_PATTERN}): (.*)(?:\r|\n|\r\n)"

# Pattern for simpler format (file:line:col: error message)
SIMPLE_PATTERN = fr"([^\r\n]*?:[0-9]+:[0-9]+: runtime error: .*?)SUMMARY: ({SANITIZER_NAME_PATTERN})"
SIMPLE_HEADER_PATTERN = fr"(.*?):([0-9]+):([0-9]+): runtime error: (.*)(?:\r|\n|\r\n)"

# Common summary pattern
SANITIZER_SUMMARY_PATTERN = fr"SUMMARY: ({SANITIZER_NAME_PATTERN}): (.*?)(?:[ \t]*(?:\r|\n|\r\n)|$)"

# Special case for LeakSanitizer
LEAK_SANITIZER_PATTERN = r"((?:==[0-9]+==)?ERROR: LeakSanitizer: detected memory leaks.*)"

# Stack trace pattern
STACK_TRACE_PATTERN = r"^\s*#(\d+)\s+(0x[\w\d]+)\s+in\s+(.+)\s+/src(.*)\s*"


class UnifiedSanitizerReport(SanitizerReport):
    def __init__(
        self,
        sanitizer: Sanitizer,
        content: str,
        cwe: str,
        trigger_point: str,
        additional_info: Dict[str, Any] = {},
    ):
        super().__init__(sanitizer, content, cwe, trigger_point, additional_info)

    def __getitem__(self, key: str) -> Any:
        return self.additional_info[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_info[key] = value

    @property
    def summary(self) -> str:
        return self.content

    @staticmethod
    def parse(raw_content: str) -> Optional["UnifiedSanitizerReport"]:
        """
        Parse sanitizer output and return a UnifiedSanitizerReport object.
        Works with all supported sanitizer types and formats.
        """
        # First try to match the traditional format with process ID
        header_match = re.search(TRADITIONAL_HEADER_PATTERN, raw_content)
        if header_match:
            sanitizer_name = header_match.group(1)
            header = header_match.group(2)
            return UnifiedSanitizerReport._parse_with_header(raw_content, sanitizer_name, header, TRADITIONAL_PATTERN)

        # Try to match the simpler format (file:line:col: runtime error)
        simple_match = re.search(SIMPLE_HEADER_PATTERN, raw_content)
        if simple_match:
            file_path = simple_match.group(1)
            line_num = simple_match.group(2)
            col_num = simple_match.group(3)
            error_msg = simple_match.group(4)

            # For this format, we need to get the sanitizer type from the summary
            summary_match = re.search(SANITIZER_SUMMARY_PATTERN, raw_content)
            if summary_match:
                sanitizer_name = summary_match.group(1)
                try:
                    sanitizer_type = Sanitizer(sanitizer_name)
                except ValueError:
                    logging.warning(
                        f"Unknown sanitizer type: {sanitizer_name}")
                    return None

                summary = summary_match.group(2)
                location = f"{file_path}:{line_num}:{col_num}"

                # Extract CWE from error message
                cwe = error_msg.split(
                    ":")[0] if ":" in error_msg else error_msg
                if "implicit conversion" in cwe:
                    cwe = "implicit conversion"  # troublesome UBSAN bug type with values in it

                # Use the file location as trigger point
                trigger_point = location if location in summary else summary

                # Special trigger point for LeakSanitizer
                if sanitizer_name == "LeakSanitizer":
                    trigger_point = "allocation(s)"

                # Get content - either use the whole report or just the relevant part
                match = re.search(SIMPLE_PATTERN, raw_content, re.DOTALL)
                content = match.group(1) if match else raw_content
                content += f"SUMMARY: {sanitizer_name}: {summary}"

                return UnifiedSanitizerReport(sanitizer_type, content, cwe, trigger_point)

        # Special case for LeakSanitizer
        leak_match = re.search(LEAK_SANITIZER_PATTERN, raw_content)
        if leak_match:
            content = leak_match.group(1)
            return UnifiedSanitizerReport(Sanitizer.LeakSanitizer, content, "memory leak", "N/A")

        # No sanitizer report found
        return None

    @staticmethod
    def _parse_with_header(raw_content: str, sanitizer_name: str, header: str, pattern: str) -> Optional["UnifiedSanitizerReport"]:
        """Helper method to parse reports with a standard header format"""
        try:
            sanitizer_type = Sanitizer(sanitizer_name)
        except ValueError:
            logging.warning(f"Unknown sanitizer type: {sanitizer_name}")
            return None

        # Look for crash report summary
        summary_match = re.search(SANITIZER_SUMMARY_PATTERN, raw_content)
        if summary_match is None:
            # Missing summary - still consider it a valid bug
            return UnifiedSanitizerReport(sanitizer_type, raw_content, header.split(" ")[0], "N/A")

        summary = summary_match.group(2)

        # Parse bug type and trigger point from header & summary
        cwe = ""
        header_words = header.split(" on ")[0].split()
        summary_words = summary.split()

        for i in range(len(header_words)):
            for j in range(i + 1, len(header_words) + 1):
                phrase = " ".join(header_words[i:j])
                if phrase in summary and len(phrase) > len(cwe):
                    cwe = phrase

        if not cwe:
            if sanitizer_name == "LeakSanitizer":
                cwe = "detected memory leaks"
            else:
                # Fallback to first word if no common substring found
                cwe = summary_words[0]

        trigger_point = summary.split(
            cwe)[1].strip() if cwe in summary else summary
        if not trigger_point:
            trigger_point = "N/A"

        # Special trigger point for LeakSanitizer
        if sanitizer_name == "LeakSanitizer":
            trigger_point = "allocation(s)"

        # Now, parse the body looking for stack traces
        match = re.search(pattern, raw_content, re.DOTALL)

        if match is None:
            # Missing body - still create a report with what we have
            return UnifiedSanitizerReport(sanitizer_type, raw_content, cwe, trigger_point)

        content = match.group(1)
        content += f"SUMMARY: {sanitizer_name}: {summary}"
        return UnifiedSanitizerReport(sanitizer_type, content, cwe, trigger_point)
