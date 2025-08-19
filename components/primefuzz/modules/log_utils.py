import logging
import sys
import asyncio
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from functools import wraps


class AsyncContextFormatter(logging.Formatter):
    def format(self, record):
        # Default values
        record.task_id = "main"
        record.project = "default"
        
        try:
            # Try to get the current task
            task = asyncio.current_task()
            if task and hasattr(task, "task_context"):
                record.task_id = task.task_context.get("task_id", "unknown")
                record.project = task.task_context.get("project", "default")
        except RuntimeError:
            # No running event loop, use default values
            pass

        return super().format(record)


def setup_logging(log_dir: Path = Path("/tmp")):
    """Setup centralized logging configuration."""
    formatter = AsyncContextFormatter(
        "%(asctime)s - [%(task_id)s|%(project)s] - %(name)s - %(funcName)s - %(levelname)s - %(message)s"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # File handler
    file_name = (
        "prime_fuzz_directed.log" if os.getenv(
            "DIRECTED_MODE") else "prime_fuzz.log"
    )
    file_handler = RotatingFileHandler(
        log_dir / file_name, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
    )
    file_handler.setFormatter(formatter)

    # Root logger config
    root_logger = logging.getLogger()
    root_logger.handlers = []  # Remove existing handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG if os.getenv(
        "LDEBUG") else logging.INFO)

    return root_logger


def set_task_context(task_id: str = None, project: str = None):
    """Set task context for current coroutine."""
    task = asyncio.current_task()
    if task:
        if not hasattr(task, "task_context"):
            task.task_context = {}
        if task_id:
            task.task_context["task_id"] = task_id
        if project:
            task.task_context["project"] = project
