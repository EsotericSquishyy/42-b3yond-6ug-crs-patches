"""
PYTHONPATH=$PYTHONPATH:$(pwd) pytest tests/test_libfuzzer_log_parser.py
"""

import pytest
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from modules.metrics_collector import MetricsCollector

REAL_LOG_CONTENT = """
#5624267: cov: 3556 ft: 5422 corp: 1133 exec/s: 1933 oom/timeout/crash: 0/0/39 time: 377s job: 52 dft_time: 0
#5624553: cov: 3556 ft: 5435 corp: 1138 exec/s: 0 oom/timeout/crash: 0/0/39 time: 377s job: 55 dft_time: 0
==450==ERROR: AddressSanitizer: dynamic-stack-buffer-overflow on address 0x7fff98086f72
#5747982: cov: 3557 ft: 5451 corp: 1147 exec/s: 6109 oom/timeout/crash: 0/0/41 time: 396s job: 57 dft_time: 0
"""


@pytest.fixture
def real_log_file(tmp_path):
    log_file = tmp_path / "real_fuzzer.log"
    log_file.write_text(REAL_LOG_CONTENT)
    return log_file


def test_parse_real_log_file(real_log_file):
    collector = MetricsCollector()
    metrics = collector.parse_log_file(real_log_file)

    assert metrics == {
        "coverage": 3557,
        "features": 5451,
        "corpus_count": 1147,
        "execs_per_sec": 6109,
        "crashes": 41,
        "time_seconds": 396,
    }


def test_ignore_error_lines(real_log_file):
    collector = MetricsCollector()
    metrics = collector.parse_log_file(real_log_file)

    # Should not contain any error information
    assert "AddressSanitizer" not in str(metrics)
    assert metrics["coverage"] > 0
