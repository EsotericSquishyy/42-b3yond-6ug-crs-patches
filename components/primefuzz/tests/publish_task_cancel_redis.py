"""
for local test only, do not run in production
"""
from pathlib import Path
import asyncio
import sys
import shutil
import os

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from modules.redis_middleware import RedisMiddleware
# jedis
MOCK_TASK_ID = "3d4d50f9-a8fd-4144-afb5-dde1ed642126"
# hikaricp
MOCK_TASK_ID = "2b8cb6fc-f3a8-4d15-aaf3-403238a456ea"
# flac
MOCK_TASK_ID = "7b64a242-5c0f-4d45-ad7d-40fd325deb17"
# logback
# zookeeper
MOCK_TASK_ID = "0195f1f6-117a-788f-aa72-a2365eade509"
MOCK_TASK_ID = "81dbd73c-adbf-4f22-a867-5d3948469638"

MOCK_JAVA_TASK = '{"diff":"/crs/81dbd73c-adbf-4f22-a867-5d3948469638/b44a889df45025a3cb74a64835a2a972a979726214eb5d28fba51f9427e755be.tar.gz","focus":"java-cp-spring-data-keyvalue","fuzzing_tooling":"/crs/81dbd73c-adbf-4f22-a867-5d3948469638/382aef11fd80035ddf6853b4fdf241114ad380200f6f89d2ad0a132f91813332.tar.gz","project_name":"spring-data-keyvalue","repo":["/crs/81dbd73c-adbf-4f22-a867-5d3948469638/a292e6ac44de2a5bda10694b29271186e33673649b6d3ead2bdeff3405c8254d.tar.gz"],"task_id":"81dbd73c-adbf-4f22-a867-5d3948469638","task_type":"delta"}'
MOCK_TAKS_METADATA = ' {"bugs":["OSV-2024-198","OSV-2024-194"],"commit":"05c147c3ef2029019f4bca856a1319b14e2a0fa8","fuzz_commit":"6af7464ca151613872f2c9732825562f67502123","latest":"05c147c3ef2029019f4bca856a1319b14e2a0fa8","oldest":"a279aae30f6c4d488f40b39e80087518b5459ea4"}'


async def set_task_metadata(middleware: RedisMiddleware, task_id: str, payload: str):
    if await middleware.set_task_metadata(task_id, payload):
        print(f"Task metadata set for task ID: {task_id}")
    else:
        print(f"Failed to set task metadata for task ID: {task_id}")


def clear_redis_content(middleware):
    middleware.redis_client.flushdb()
    # rm -rf /crs/public_build/$MOCK_TASK_ID
    # rm -rf /tmp/javaslice/$MOCK_TASK_ID
    try:
        if os.path.exists(f"/crs/public_build/{MOCK_TASK_ID}"):
            shutil.rmtree(f"/crs/public_build/{MOCK_TASK_ID}")
        if os.path.exists(f"/tmp/javaslice/{MOCK_TASK_ID}"):
            shutil.rmtree(f"/tmp/javaslice/{MOCK_TASK_ID}")
        print(f"Removed directories for task ID: {MOCK_TASK_ID}")
    except Exception as e:
        print(f"Error removing directories: {e}")


async def main():
    middleware = RedisMiddleware()
    # Test setting valid status
    result = middleware.remove_global_task_status(MOCK_TASK_ID)
    if len(sys.argv) > 1:
        if sys.argv[1] == "slice":
            print("slice")
            result = await middleware.record_slice_task(MOCK_TASK_ID, MOCK_JAVA_TASK)
        elif sys.argv[1] == "clear":
            print("clear redis DB")
            clear_redis_content(middleware)
        elif sys.argv[1] == "metadata":
            print("set task metadata")
            await set_task_metadata(middleware, MOCK_TASK_ID, MOCK_TAKS_METADATA)
        else:
            result = await middleware.set_global_task_status(MOCK_TASK_ID, "canceled")
        
        print(result)

if __name__ == "__main__":
    asyncio.run(main())
