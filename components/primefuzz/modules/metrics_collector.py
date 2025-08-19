import re
import json
import logging
from pathlib import Path
from typing import Dict, Any
from collections import deque

logger = logging.getLogger(__name__)


class MetricsCollector:
    def __init__(self):
        self.log_pattern = re.compile(
            r"#\d+:\s+cov:\s+(\d+)\s+ft:\s+(\d+)\s+corp:\s+(\d+)\s+exec/s:\s+(\d+)"
            r".*?oom/timeout/crash:\s+\d+/\d+/(\d+)\s+time:\s+(\d+)s"
        )

        # Add backup patterns for individual metrics
        self.coverage_pattern = re.compile(r"cov:\s+(\d+)")
        self.features_pattern = re.compile(r"ft:\s+(\d+)")
        self.corpus_pattern = re.compile(r"corp:\s+(\d+)")
        self.execs_pattern = re.compile(r"exec/s:\s+(\d+)")

        self.re_libfuzzer_status = re.compile(
            r"\s*#(\d+)\s+(INITED|NEW|RELOAD|REDUCE|pulse)\s+cov:"
        )
        self.MAX_LINES = 1000

    def _read_last_n_lines(self, file_path: Path, n: int) -> str:
        try:
            with open(file_path, "r") as f:
                return "".join(deque(f, n))
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return ""

    def parse_log_file(self, log_file: Path) -> Dict[str, Any]:
        try:
            content = self._read_last_n_lines(log_file, self.MAX_LINES)
            if not content:
                return {}

            # Try main pattern first
            matches = [m for m in self.log_pattern.finditer(content)]
            if matches:
                last_match = matches[-1]
                return {
                    "coverage": int(last_match.group(1)),
                    "features": int(last_match.group(2)),
                    "corpus_count": int(last_match.group(3)),
                    "execs_per_sec": int(last_match.group(4)),
                    "crashes": int(last_match.group(5)),
                    "time_seconds": int(last_match.group(6)),
                }

            # If main pattern fails, try backup patterns
            result = {}
            lines = content.splitlines()
            last_line = lines[-1] if lines else ""

            # Try to match individual metrics from the last line
            if cov_match := self.coverage_pattern.search(last_line):
                result["coverage"] = int(cov_match.group(1))
                
            if ft_match := self.features_pattern.search(last_line):
                result["features"] = int(ft_match.group(1))
                
            if corp_match := self.corpus_pattern.search(last_line):
                # Extract just the first number before the slash
                corp_value = corp_match.group(1).split('/')[0]
                result["corpus_count"] = int(corp_value)
                
            if exec_match := self.execs_pattern.search(last_line):
                result["execs_per_sec"] = int(exec_match.group(1))

            return result

        except Exception as e:
            logger.error(f"Error parsing log file {log_file}: {e}")
            return {}
