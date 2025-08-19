"""
Jazzer sanitizer pattern:

== Java Exception:com.code_intelligence.jazzer.api.FuzzerSecurityIssue.*

* com.code_intelligence.jazzer.api.FuzzerSecurityIssueMedium: Server Side Request Forgery (SSRF)
* FuzzerSecurityIssueCritical: File path traversal
* FuzzerSecurityIssueCritical: LDAP Injection
* FuzzerSecurityIssueCritical: Remote JNDI Lookup
* FuzzerSecurityIssueCritical: OS Command Injection
* FuzzerSecurityIssueCritical: Script Engine Injection: Insecure user input was used in script engine
* FuzzerSecurityIssueHigh: load arbitrary library
* FuzzerSecurityIssueHigh: SQL Injection
* FuzzerSecurityIssueHigh: XPath Injection
* FuzzerSecurityIssueHigh: Remote Code Execution
* FuzzerSecurityIssueLow: Regular Expression Injection 

OOM:
== Java Exception: com.code_intelligence.jazzer.api.FuzzerSecurityIssueLow: Out of memory (use '-Xmx720m' to reproduce)
Caused by: java.lang.OutOfMemoryError: GC overhead limit exceeded
        at java.base/java.lang.StringLatin1.toChars(StringLatin1.java:74)
        at java.base/java.lang.String.encodeWithEncoder(String.java:878)
        at java.base/java.lang.String.encode(String.java:843)
        at java.base/java.lang.String.getBytes(String.java:1788)
DEDUP_TOKEN: e27ce7b4126d66a4
== libFuzzer crashing input ==

Timeout:
==14== ERROR: libFuzzer: timeout after 25 seconds

Stack traces of all JVM threads:
Thread[Finalizer,8,system]
        at java.base@17.0.14/java.lang.Object.wait(Native Method)
        at java.base@17.0.14/java.lang.ref.ReferenceQueue.remove(ReferenceQueue.java:155)
        at java.base@17.0.14/java.lang.ref.ReferenceQueue.remove(ReferenceQueue.java:176)
        at java.base@17.0.14/java.lang.ref.Finalizer$FinalizerThread.run(Finalizer.java:172)

Thread[Attach Listener,9,system]

Thread[main,5,main]
        at app//com.code_intelligence.jazzer.driver.FuzzTargetRunner.dumpAllStackTraces(FuzzTargetRunner.java:534)

Thread[Common-Cleaner,8,InnocuousThreadGroup]
        at java.base@17.0.14/java.lang.Object.wait(Native Method)
        at java.base@17.0.14/java.lang.ref.ReferenceQueue.remove(ReferenceQueue.java:155)
        at java.base@17.0.14/jdk.internal.ref.CleanerImpl.run(CleanerImpl.java:140)
        at java.base@17.0.14/java.lang.Thread.run(Thread.java:840)
        at java.base@17.0.14/jdk.internal.misc.InnocuousThread.run(InnocuousThread.java:162)

Thread[Notification Thread,9,system]

Thread[Reference Handler,10,system]
        at java.base@17.0.14/java.lang.ref.Reference.waitForReferencePendingList(Native Method)
        at java.base@17.0.14/java.lang.ref.Reference.processPendingReferences(Reference.java:253)
        at java.base@17.0.14/java.lang.ref.Reference$ReferenceHandler.run(Reference.java:215)

Thread[Signal Dispatcher,9,system]

Thread[process reaper,10,system]
        at java.base@17.0.14/jdk.internal.misc.Unsafe.park(Native Method)
        at java.base@17.0.14/java.util.concurrent.locks.LockSupport.parkNanos(LockSupport.java:252)
        at java.base@17.0.14/java.util.concurrent.SynchronousQueue$TransferStack.transfer(SynchronousQueue.java:401)
        at java.base@17.0.14/java.util.concurrent.SynchronousQueue.poll(SynchronousQueue.java:903)
        at java.base@17.0.14/java.util.concurrent.ThreadPoolExecutor.getTask(ThreadPoolExecutor.java:1061)
        at java.base@17.0.14/java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1122)
        at java.base@17.0.14/java.util.concurrent.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:635)
        at java.base@17.0.14/java.lang.Thread.run(Thread.java:840)

Garbage collector stats:

PS MarkSweep: 0 collections took 0ms
PS Scavenge: 15 collections took 467ms

SUMMARY: libFuzzer: timeout
"""

import asyncio
import logging
import asyncio
import logging
import subprocess
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


UNKNOWN_STRING = "Unknown"
TIMEOUT_STRING = "Timeout"
OOM_STRING = "Out of memory"
PADDING_STRING = "Padding"


class SanitizerType(Enum):
    ASAN = "address"
    UBSAN = "undefined"
    MSAN = "memory"
    JAZZER = "address"
    UNKNOWN = "none"


@dataclass
class CrashInfo:
    bug_type: str
    trigger_point: str
    summary: str
    harness_name: str
    poc: str
    sanitizer: str
    sarif_report: Dict[str, Any]
    raw_output: str = ""
    dup_token: str = ""


class CrashTriager:
    def __init__(self, oss_fuzz_path: Path):
        self.oss_fuzz_path = oss_fuzz_path
        # Jazzer pattern
        self.jazzer_pattern = re.compile(
            r"==\s*Java Exception:\s*(com\.code_intelligence\.jazzer\.api\.FuzzerSecurityIssue\w+):\s*(.*?)(?=\n|$)"
        )
        # Match "SUMMARY: <Sanitizer>: <bug description>"
        self.c_bug_type_pattern = re.compile(
            r"SUMMARY:\s*(AddressSanitizer|UndefinedBehaviorSanitizer):\s*(.*?)(?=\s+|$)"
        )
        # Match "SUMMARY: <file>:<line> in <function>"
        self.c_location_pattern = re.compile(
            r"SUMMARY:.*?(?:[\w/\-\.]+\.(?:c|cc|cpp|h|hpp)):(\d+)(?::\d+)?\s+(?:in\s+(.+))?"
        )
        self.stack_trace_pattern = re.compile(r"\s*#\d+\s")
        # dedup token pattern
        # DEDUP_TOKEN: function_1--function_name--LLVMFuzzerTestOneInput
        self.dedup_token_pattern = re.compile(r"DEDUP_TOKEN:\s*([^\n]+)")
        # timeout pattern
        # ==15== ERROR: libFuzzer: timeout after 2 seconds
        self.timeout_pattern = re.compile(
            r"==\d*==\s*ERROR:\s*libFuzzer: timeout after\s\d+\sseconds")
        self.timeout_kwd = "SUMMARY: libFuzzer: timeout"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def cleanup(self):
        """Cleanup resources."""
        # Add cleanup logic here
        logger.debug("Cleaning up CrashTriager resources")

    def extract_dedup_token(self, output: str) -> str:
        """Extract deduplication token from crash output."""
        if match := self.dedup_token_pattern.search(output):
            return match.group(1)
        return "Unknown"

    def format_summary_lines(self, output: str, max_lines: int = 5) -> str:
        """Format stack trace summary lines from crash output.

        Args:
            output: Raw crash output text
            max_lines: Maximum number of stack trace lines to include

        Returns:
            Formatted summary string with stack traces
        """
        summary_lines = []
        for line in output.splitlines():
            if self.stack_trace_pattern.match(line):
                # Split on ' in ' and keep the part after if exists
                parts = line.split(" in ", 1)
                if len(parts) > 1:
                    summary_lines.append(parts[1].strip())
                else:
                    summary_lines.append(line.strip())
        return "\n".join(summary_lines[:max_lines])

    def _try_decode(self, data: bytes) -> str:
        """Try different encodings to decode binary data."""
        encodings = ["utf-8", "latin1", "ascii"]
        logger.debug(f"Trying to decode data with encodings: {encodings}")
        for encoding in encodings:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                logger.debug(f"Failed to decode with {encoding}")
        raise UnicodeDecodeError("Failed to decode with all encodings")

    def _detect_sanitizer(self, output: str):
        if "Java Exception:" in output:
            return SanitizerType.JAZZER
        elif "AddressSanitizer" in output:
            return SanitizerType.ASAN
        elif "UndefinedBehaviorSanitizer" in output:
            return SanitizerType.UBSAN
        return SanitizerType.UNKNOWN

    def _extract_java_location(self, output: str) -> str:
        for line in output.splitlines():
            if "at " in line and ".java:" in line:
                return line.strip().replace("\tat ", "")
        return UNKNOWN_STRING

    def _extract_bug_info(self, output: str, sanitizer: str) -> tuple[str, str]:
        # First check for timeout
        if self.timeout_pattern.search(output) or self.timeout_kwd in output:
            return TIMEOUT_STRING, UNKNOWN_STRING

        if sanitizer == SanitizerType.JAZZER:
            match = self.jazzer_pattern.search(output)
            if match:
                severity = match.group(1).replace(
                    "com.code_intelligence.jazzer.api.", ""
                )
                description = match.group(2).strip()
                return f"{severity}: {description}", self._extract_java_location(output)
        else:
            bug_match = self.c_bug_type_pattern.search(output)
            loc_match = self.c_location_pattern.search(output)
            if bug_match:
                bug_type = f"{bug_match.group(1)}: {bug_match.group(2)}"
                trigger_point = (
                    loc_match.group(0).replace("SUMMARY: ", "", 1)
                    if loc_match
                    else UNKNOWN_STRING
                )
                return bug_type, trigger_point
        return UNKNOWN_STRING, UNKNOWN_STRING

    def extract_timeout_info(self, output: str) -> Optional[str]:
        """Extract timeout information from crash output.

        Args:
            output: Raw crash output text

        Returns:
            The timeout message if found, None otherwise
        """
        # Match patterns like "libFuzzer: timeout after 25 seconds"
        timeout_detail_pattern = re.compile(
            r"libFuzzer: timeout after (\d+) seconds")

        if match := timeout_detail_pattern.search(output):
            return f"libFuzzer: timeout after {match.group(1)} seconds"

        # Fallback to check if it's a timeout without specific details
        if self.timeout_pattern.search(output) or self.timeout_kwd in output:
            return "libFuzzer: timeout"

        return None

    def extract_thread_info(self, output: str) -> list[dict]:
        """Extract information about JVM threads from crash output.

        Args:
            output: Raw crash output text

        Returns:
            List of dictionaries containing thread information
        """
        thread_info = []

        # Check if this is a JVM stack trace dump
        if "Stack traces of all JVM threads:" not in output:
            return thread_info

        # Extract thread information using regex
        thread_pattern = re.compile(r"Thread\[([^,]+),(\d+),([^\]]+)\]")

        for match in thread_pattern.finditer(output):
            thread_name = match.group(1)
            thread_priority = int(match.group(2))
            thread_group = match.group(3)

            # Find the stack trace for this thread
            start_pos = match.end()
            next_thread = thread_pattern.search(output, start_pos)
            end_pos = next_thread.start() if next_thread else len(output)

            # Extract stack trace
            stack_trace_text = output[start_pos:end_pos].strip()
            stack_trace_lines = [
                line.strip() for line in stack_trace_text.split('\n') if line.strip()]

            thread_info.append({
                "name": thread_name,
                "priority": thread_priority,
                "group": thread_group,
                "stack_trace": stack_trace_lines
            })

        return thread_info

    async def triage_crash(
        self, project_name: str, fuzzer_name: str, crash_file: Path
    ) -> Optional[CrashInfo]:
        try:
            # Run helper.py reproduce
            cmd = [
                "python3",
                "infra/helper.py",
                "reproduce",
                project_name,
                fuzzer_name,
                str(crash_file),
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.oss_fuzz_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            try:
                output = self._try_decode(stdout + stderr)
            except UnicodeDecodeError as e:
                logger.error(f"Failed to decode process output: {e}")
                return None

            if process.returncode == 0:
                logger.error(
                    f"Crash reproduction failed, the fuzzer did not crash: {output[-1024:]}"
                )
                return None

            if process.returncode == 70 or "ERROR: libFuzzer: timeout after" in output:
                # This means timeout
                logger.info(
                    f"Crash reproduction with libFuzzer timeout: {output[-128:]}"
                )
                thread_info = self.extract_thread_info(output)
                timeout_dup_token = thread_info[0]['name'] + \
                    str(thread_info[0]['priority']) + \
                    str(thread_info[0]['group']) if len(
                        thread_info) > 0 else "Unknown"
                return CrashInfo(
                    bug_type=TIMEOUT_STRING,
                    trigger_point=thread_info[0]['name'] if len(
                        thread_info) > 0 else UNKNOWN_STRING,
                    summary=self.extract_timeout_info(
                        output) or UNKNOWN_STRING,
                    raw_output=output,
                    sanitizer=SanitizerType.UNKNOWN.value,
                    harness_name=fuzzer_name,
                    poc=str(crash_file),
                    dup_token=timeout_dup_token,
                    sarif_report={"version": "2.1.0", "runs": []},
                )

            # Parse output
            bug_type = UNKNOWN_STRING
            trigger_point = UNKNOWN_STRING

            # Extract bug type
            sanitizer = self._detect_sanitizer(output)
            bug_type, trigger_point = self._extract_bug_info(output, sanitizer)
            summary = self.format_summary_lines(output)
            dup_token = self.extract_dedup_token(output).rstrip()

            return CrashInfo(
                bug_type=bug_type,
                trigger_point=trigger_point,
                summary=summary,
                raw_output=output,
                sanitizer=sanitizer.value,
                harness_name=fuzzer_name,
                poc=str(crash_file),
                dup_token=dup_token,
                sarif_report={"version": "2.1.0", "runs": []},
            )

        except Exception as e:
            logger.error(f"Error during crash triage: {e}")
            return None

    async def triage_crash_log(self, logfile: Path, harness_name: str) -> Optional[CrashInfo]:
        """Triage a crash from log file containing crash output.

        Args:
            logfile: Path to log file containing crash output

        Returns:
            CrashInfo object if crash can be parsed, None otherwise
        """
        try:
            # Read log file content
            with open(logfile, 'r') as f:
                output = f.read()

            if not output:
                logger.error(f"Empty log file: {logfile}")
                return None

            # Detect sanitizer and extract bug info
            sanitizer = self._detect_sanitizer(output)
            bug_type, trigger_point = self._extract_bug_info(output, sanitizer)

            # Get stack trace summary and dedup token
            summary = self.format_summary_lines(output)
            dup_token = self.extract_dedup_token(output).rstrip()

            return CrashInfo(
                bug_type=bug_type,
                trigger_point=trigger_point,
                summary=summary,
                raw_output=output,
                sanitizer=sanitizer.value,
                harness_name=harness_name,
                poc=str(logfile),
                dup_token=dup_token,
                sarif_report={"version": "2.1.0", "runs": []}
            )

        except Exception as e:
            logger.error(f"Error triaging crash log {logfile}: {e}")
            return None
