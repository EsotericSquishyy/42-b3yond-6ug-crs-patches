"""
triage local crash
python3 infra/helper.py reproduce libpng libpng_read_fuzzer /tmp/sample_data.bin
"""

from pathlib import Path
import sys
import asyncio
import pprint
import uuid

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from db.db_manager import DBManager
from modules.triage import CrashTriager, CrashInfo

OSS_FUZZ_PATH = "/mydata/data/code/oss-fuzz"
LOCAL_TESTCASE_PATH = "/crs/crash_backup/prime/b112a8fe-b98e-44f9-b94b-305a3dba82a0/jedis_URIfuzzer.bin"
MOCK_TASK_ID = "b112a8fe-b98e-44f9-b94b-305a3dba82a0"


async def store_crash_info(crash_info: CrashInfo):
    db = DBManager()
    # Generate a mock task ID since this is a test
    test_task_id = MOCK_TASK_ID
    db.set_enable_bug_profiling()
    await db.store_bug_profile_info(test_task_id, crash_info)
    return test_task_id


async def test_crash_triager():
    triager = CrashTriager(Path(OSS_FUZZ_PATH))
    crash_info = await triager.triage_crash(
        "libpng", "libpng_read_fuzzer", Path(LOCAL_TESTCASE_PATH))

    print(f"Bug type = {crash_info.bug_type}")
    print(f"trigger_point = {crash_info.trigger_point=}")
    print("Summary:")
    # pprint.pprint(crash_info.summary)

    assert isinstance(crash_info, CrashInfo)

    assert crash_info.bug_type == "AddressSanitizer: dynamic-stack-buffer-overflow"

    # Store crash info in database
    task_id = await store_crash_info(crash_info)
    print(f"Stored crash info in database with task ID: {task_id}")


async def test_crash_triager_jvm():
    triager = CrashTriager(Path(OSS_FUZZ_PATH))
    crash_info = await triager.triage_crash(
        "jedis", "JedisURIFuzzer", Path(LOCAL_TESTCASE_PATH))

    print(f"Bug type = {crash_info.bug_type}")
    print(f"Sanitizer = {crash_info.sanitizer}")
    print(f"trigger_point = {crash_info.trigger_point}")
    print("Summary(DUP_TOKEN for JVM):")
    pprint.pprint(crash_info.dup_token)

    assert isinstance(crash_info, CrashInfo)

    assert crash_info.sanitizer == "JAZZER"
    # print(f"Crash info: {crash_info}")

    # Store crash info in database
    task_id = await store_crash_info(crash_info)
    print(f"Stored crash info in database with task ID: {task_id}")

if __name__ == "__main__":
    # asyncio.run(test_crash_triager())
    asyncio.run(test_crash_triager_jvm())
