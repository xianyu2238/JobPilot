"""Configure console logs without logging settings or request payloads."""

import logging


def configure_logging(level: str) -> None:
    logger = logging.getLogger("jobpilot")
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
    logger.info("Application logging initialized")
