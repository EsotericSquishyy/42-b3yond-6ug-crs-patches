import logging

from patch_generator.telemetry import patchagent_hook, telemetry_hook
from patchagent.logger import logger as patchagent_logger

logger = logging.getLogger("aixcc")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(message)s"))

logger.addHandler(console_handler)


def init_logger() -> None:
    logger.info("[🔌] Initializing logger system...")
    telemetry_hook([logger, patchagent_logger])
    logger.info("[✅] Telemetry hook successfully configured")

    patchagent_hook(patchagent_logger)
    logger.info("[✅] Database error recorder successfully configured")
