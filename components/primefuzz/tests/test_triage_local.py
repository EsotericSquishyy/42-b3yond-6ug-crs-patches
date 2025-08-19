"""
triage local crash
python3 infra/helper.py reproduce libpng libpng_read_fuzzer /tmp/sample_data.bin
"""

import pytest
from pathlib import Path
import sys
import base64

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
OSS_FUZZ_PATH = "/mydata/data/code/oss-fuzz"

from modules.triage import CrashTriager, CrashInfo


@pytest.fixture
def testcase_path(tmp_path):
    test_case_file = tmp_path / "sample_data.bin"
    b64_data = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgEAIAAACsiDHgAAAABHNCSVRnQU1BAAGGoDHoll9pQ0NQdFJOU////////569S9jEYlOYYsAWlqG1o2UjoXY8XB0iIEygVJTCutJSWgodHWUQGA43tzkHok40OnFkOmYMMWbMRONzD7a5qfH9f6A2WVC6Z0lGdMvljt73/3/////////////////////////////////////////////////////////////////////////////////////////////vO/H7/5z4rwO4WAuSwOfkADlNFqIUNg8JfE32kjpSQEpKHgZ1dXeArVvTwNiYCxw7NgUAAJbnSLAAAAAEZ0FNQQABhqAx6JZfAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAENvcHlyaWdodACpILYgnxaPEhfhWYu/dyxEWQv4cfcc4e+kC1fK//7r9B+bDPkeC/hx9xzh76QLV8r//uv0H5sM+R76omEaAAAgAElFTkSuQmCC"
    test_file = Path(test_case_file)
    test_file.write_bytes(base64.b64decode(b64_data))
    return test_file


@pytest.fixture
def testcase_path_jvm(tmp_path):
    test_case_file = tmp_path / "sample_data.bin"
    b64_data = "Wlo6Ly8yNjg0Nzo2NDg5LzQ="
    test_file = Path(test_case_file)
    test_file.write_bytes(base64.b64decode(b64_data))
    return test_file


@pytest.mark.asyncio
async def test_crash_triager_libpng(testcase_path):
    triager = CrashTriager(Path(OSS_FUZZ_PATH))
    crash_info = await triager.triage_crash(
        "libpng", "libpng_read_fuzzer", testcase_path
    )

    assert isinstance(crash_info, CrashInfo)
    assert "AddressSanitizer" in crash_info.bug_type
    assert "dynamic-stack-buffer-overflow" in crash_info.bug_type
    assert (
        crash_info.dup_token
        == "OSS_FUZZ_png_handle_iCCP--OSS_FUZZ_png_read_info--LLVMFuzzerTestOneInput"
    )


@pytest.mark.asyncio
async def test_crash_triager_jedis(testcase_path_jvm):
    triager = CrashTriager(Path(OSS_FUZZ_PATH))
    crash_info = await triager.triage_crash(
        "jedis", "JedisURIFuzzer", testcase_path_jvm
    )

    assert isinstance(crash_info, CrashInfo)
    assert crash_info.sanitizer == "JAZZER"
    assert "FuzzerSecurityIssue" in crash_info.bug_type
    assert "SSRF" in crash_info.bug_type
    assert crash_info.dup_token == "f95d15ae9fd3c8fc"
