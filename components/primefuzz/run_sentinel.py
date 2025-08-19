import asyncio
import logging
from pathlib import Path
from modules.config import Config
from sentinel import TaskSentinel
from modules.log_utils import setup_logging

log_path = Path("/tmp/sentinel/")
log_path.mkdir(exist_ok=True)

setup_logging(log_path)
logger = logging.getLogger(__name__)


async def main():
    try:
        config = Config.from_env()
        sentinel = TaskSentinel(config)

        logger.info("Starting standalone sentinel service...")
        await sentinel.run()
    except KeyboardInterrupt:
        logger.info("Shutting down sentinel service...")
    except Exception as e:
        logger.error(f"Fatal error in sentinel service: {e}")
        return 1
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
