import re
import hashlib
import logging
from typing import List, Optional, Tuple, Dict
from enum import Enum
from pathlib import Path

from parser.sanitizer import Sanitizer, SanitizerReport

# Regex patterns for Jazzer outputs
JazzerExceptionPattern = r"==\s*Java Exception:\s*(com\.code_intelligence\.jazzer\.api\.FuzzerSecurityIssue\w+):\s*(.*?)(?=\n|$)"
JazzerStackTracePattern = r"^\s*at\s+([^(]+)\(([^:]+):(\d+)\)"
JazzerDedupTokenPattern = r"DEDUP_TOKEN:\s*([^\n]+)"
JazzerTimeoutPattern = r"==\d*==\s*ERROR:\s*libFuzzer: timeout after\s\d+\sseconds"
JazzerOOMPattern = r"(Out of memory.*?)(?=\n|Caused by:|$)"

# Mapping of Jazzer exception types to CWE categories
JAZZER_CWE_MAP = {
    "FuzzerSecurityIssueMedium: Server Side Request Forgery": "CWE-918",
    "FuzzerSecurityIssueCritical: File path traversal": "CWE-22",
    "FuzzerSecurityIssueCritical: LDAP Injection": "CWE-90",
    "FuzzerSecurityIssueCritical: Remote JNDI Lookup": "CWE-470",
    "FuzzerSecurityIssueCritical: OS Command Injection": "CWE-78",
    "FuzzerSecurityIssueCritical: Script Engine Injection": "CWE-94",
    "FuzzerSecurityIssueHigh: load arbitrary library": "CWE-114",
    "FuzzerSecurityIssueHigh: SQL Injection": "CWE-89",
    "FuzzerSecurityIssueHigh: XPath Injection": "CWE-643",
    "FuzzerSecurityIssueHigh: Remote Code Execution": "CWE-94",
    "FuzzerSecurityIssueLow: Regular Expression Injection": "CWE-185",
    "FuzzerSecurityIssueLow: Out of memory": "CWE-400"
}


class JazzerSanitizerReport(SanitizerReport):
    """Report for Jazzer sanitizer findings."""

    def __init__(
        self,
        content: str,
        cwe: str,
        trigger_point: str,
        exception_type: str = None,
        stack_traces: List[str] = None,
        dedup_token: str = None
    ):
        super().__init__(Sanitizer.Jazzer, content, cwe, trigger_point)
        self.exception_type = exception_type
        self.stack_traces = stack_traces or []
        self.dedup_token = dedup_token

    @property
    def summary(self) -> str:
        """Generate a summary hash of the report content."""
        return self.content

    def get_cwe_id(self) -> str:
        """Map Jazzer exception to CWE ID."""
        for key, cwe in JAZZER_CWE_MAP.items():
            if key in self.cwe:
                return cwe
        return "CWE-0"  # Unknown/unclassified

    @staticmethod
    def parse(raw_content: str) -> Optional["JazzerSanitizerReport"]:
        """Parse Jazzer sanitizer output and create a report.

        Args:
            raw_content: Raw output from Jazzer sanitizer

        Returns:
            JazzerSanitizerReport object if parsing is successful, None otherwise
        """
        # Check for timeout
        if re.search(JazzerTimeoutPattern, raw_content) or "SUMMARY: libFuzzer: timeout" in raw_content:
            return JazzerSanitizerReport(
                raw_content,
                "timeout",
                "N/A",
                exception_type="Timeout",
                dedup_token="timeout"
            )

        # Check for OOM
        oom_match = re.search(JazzerOOMPattern, raw_content)
        if oom_match or "OutOfMemoryError" in raw_content:
            oom_detail = oom_match.group(
                1) if oom_match else "OutOfMemoryError"
            return JazzerSanitizerReport(
                raw_content,
                "Out of memory",
                "N/A",
                exception_type="OutOfMemoryError",
                dedup_token="oom"
            )

        # Look for Jazzer exception
        match = re.search(JazzerExceptionPattern, raw_content)
        if match is None:
            logging.debug("No Jazzer exception detected")
            return None

        exception_class = match.group(1)
        exception_message = match.group(2)

        # Clean up exception class name
        exception_type = exception_class.replace(
            "com.code_intelligence.jazzer.api.", "")
        cwe = f"{exception_type}: {exception_message}"

        # Extract stack traces
        stack_traces = []
        for trace_match in re.finditer(JazzerStackTracePattern, raw_content, re.MULTILINE):
            method = trace_match.group(1)
            file_path = trace_match.group(2)
            line_num = trace_match.group(3)
            stack_traces.append(f"{method} ({file_path}:{line_num})")

        # Use first stack trace as trigger point, or N/A if none found
        trigger_point = stack_traces[0] if stack_traces else "N/A"

        # Extract deduplication token if available
        dedup_match = re.search(JazzerDedupTokenPattern, raw_content)
        dedup_token = dedup_match.group(1) if dedup_match else None

        return JazzerSanitizerReport(
            raw_content,
            cwe,
            trigger_point,
            exception_type=exception_type,
            stack_traces=stack_traces,
            dedup_token=dedup_token
        )

    def to_dict(self) -> Dict:
        """Convert the report to a dictionary."""
        base_dict = super().to_dict()
        base_dict.update({
            "exception_type": self.exception_type,
            "stack_traces": self.stack_traces,
            "dedup_token": self.dedup_token,
            "cwe_id": self.get_cwe_id()
        })
        return base_dict
