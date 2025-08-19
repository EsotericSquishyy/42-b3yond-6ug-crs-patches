"""
PYTHONPATH=$PYTHONPATH:$(pwd) pytest tests/xxx.py
"""

import pytest
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from modules.redis_middleware import RedisMiddleware

MOCK_TASK_ID = "3d4d50f9-a8fd-4144-afb5-dde1ed642126"


@pytest.fixture
async def redis_middleware():
    middleware = RedisMiddleware()
    yield middleware
    # Cleanup after tests
    status_key = f"global:task_status:{MOCK_TASK_ID}"
    middleware.redis_client.delete(status_key)


@pytest.mark.asyncio
async def test_set_global_task_status(redis_middleware):
    # Test setting valid status
    result = await redis_middleware.set_global_task_status(MOCK_TASK_ID, "processing")
    assert result is True

    # Test setting invalid status
    result = await redis_middleware.set_global_task_status(MOCK_TASK_ID, "invalid_status")
    assert result is False


@pytest.mark.asyncio
async def test_get_global_task_status(redis_middleware):
    # Test getting non-existent status
    status = redis_middleware.get_global_task_status(MOCK_TASK_ID)
    assert status is None

    # Set and get status
    await redis_middleware.set_global_task_status(MOCK_TASK_ID, "processing")
    status = redis_middleware.get_global_task_status(MOCK_TASK_ID)
    assert status == "processing"

    # Update and verify status
    await redis_middleware.set_global_task_status(MOCK_TASK_ID, "canceled")
    status = redis_middleware.get_global_task_status(MOCK_TASK_ID)
    assert status == "canceled"
